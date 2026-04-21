#!/usr/bin/env python3
"""
Claude transcript 采集模块。

负责配置读取、日志、状态、payload 解析、transcript 增量读取与 turn 构建。
"""

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_SESSION_ID = ""


class CollectorConfig:
    """Runtime config and path resolver for the collector layer."""

    TRACE_TO_LANGFUSE = "TRACE_TO_LANGFUSE"
    LANGFUSE_PUBLIC_KEY = "LANGFUSE_PUBLIC_KEY"
    LANGFUSE_SECRET_KEY = "LANGFUSE_SECRET_KEY"
    LANGFUSE_BASE_URL = "LANGFUSE_BASE_URL"

    LANGFUSE_DEBUG = "LANGFUSE_DEBUG"
    LANGFUSE_MAX_CHARS = "LANGFUSE_MAX_CHARS"

    REMOVE_KEYS = (
        TRACE_TO_LANGFUSE,
        LANGFUSE_PUBLIC_KEY,
        LANGFUSE_SECRET_KEY,
        LANGFUSE_BASE_URL,
        LANGFUSE_DEBUG,
        LANGFUSE_MAX_CHARS,
    )

    def __init__(self) -> None:
        self.home_dir = Path.home()
        self.settings_file = self.home_dir / ".claude" / "settings.local.json"
        self.state_dir = self.home_dir / ".claude" / "state"
        self.log_file = self.state_dir / "langfuse_hook.log"
        self.state_file = self.state_dir / "langfuse_state.json"
        self.lock_file = self.state_dir / "langfuse_state.lock"
        self.settings_env = self._read_settings_env()
        self.trace_enabled = self._read_trace_enabled()
        self.public_key = self._read_required_value(self.LANGFUSE_PUBLIC_KEY)
        self.secret_key = self._read_required_value(self.LANGFUSE_SECRET_KEY)
        self.base_url = self._read_required_value(self.LANGFUSE_BASE_URL)
        self.max_chars = self._read_max_chars()
        self.debug_enabled = self._read_debug_enabled()

    def _read_settings_env(self) -> Dict[str, str]:
        try:
            if not self.settings_file.exists():
                return {}
            settings = json.loads(self.settings_file.read_text(encoding="utf-8"))
            env = settings.get("env")
            if isinstance(env, dict):
                return {str(k): str(v) for k, v in env.items()}
        except Exception:
            pass
        return {}

    def _get_config_value(self, name: str) -> str:
        value = os.environ.get(name)
        if value:
            return value
        return self.settings_env.get(name, "")

    def _read_required_value(self, name: str) -> str:
        return self._get_config_value(name)

    def _read_trace_enabled(self) -> bool:
        return self._get_config_value(self.TRACE_TO_LANGFUSE).lower() == "true"

    def _read_max_chars(self) -> int:
        raw_value = self._get_config_value(self.LANGFUSE_MAX_CHARS)
        try:
            return int(raw_value or "20000")
        except ValueError:
            return 20000

    def _read_debug_enabled(self) -> bool:
        return self._get_config_value(self.LANGFUSE_DEBUG).lower() == "true"

    def get_state_dir(self) -> Path:
        return self.state_dir

    def get_log_file(self) -> Path:
        return self.log_file

    def get_state_file(self) -> Path:
        return self.state_file

    def get_lock_file(self) -> Path:
        return self.lock_file

    def get_settings_file(self) -> Path:
        return self.settings_file


CONFIG = CollectorConfig()


def refresh_config() -> CollectorConfig:
    """Refresh the module-level runtime config from current HOME and env."""
    global CONFIG
    CONFIG = CollectorConfig()
    return CONFIG


def set_current_session_id(session_id: str) -> None:
    """Set the session id carried by subsequent log lines."""
    global CURRENT_SESSION_ID
    CURRENT_SESSION_ID = session_id


def is_debug_enabled() -> bool:
    """Whether debug logging is enabled for the current hook execution."""
    runtime_config = CONFIG
    return runtime_config.debug_enabled


def _log(level: str, message: str) -> None:
    try:
        state_dir = CONFIG.get_state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(CONFIG.get_log_file(), "a", encoding="utf-8") as f:
            f.write(f"{ts} [{level}][{CURRENT_SESSION_ID}] {message}\n")
    except Exception:
        pass


def debug(msg: str) -> None:
    if is_debug_enabled():
        _log("DEBUG", msg)


def info(msg: str) -> None:
    _log("INFO", msg)


def warn(msg: str) -> None:
    _log("WARN", msg)


def error(msg: str) -> None:
    _log("ERROR", msg)


class FileLock:
    """Best-effort file lock for protecting state updates."""

    def __init__(self, path: Path, timeout_s: float = 2.0):
        self.path = path
        self.timeout_s = timeout_s
        self._fh = None

    def __enter__(self):
        CONFIG.get_state_dir().mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+", encoding="utf-8")
        try:
            import fcntl

            deadline = time.time() + self.timeout_s
            while True:
                try:
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.time() > deadline:
                        break
                    time.sleep(0.05)
        except Exception:
            pass
        return self

    def __exit__(self, exc_type, exc, tb):
        fh = self._fh
        if fh is None:
            return
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass


def load_state() -> Dict[str, Any]:
    """Load persisted global hook state."""
    try:
        state_file = CONFIG.get_state_file()
        if not state_file.exists():
            return {}
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    """Persist global hook state atomically."""
    try:
        state_dir = CONFIG.get_state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = CONFIG.get_state_file()
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, state_file)
    except Exception as e:
        debug(f"save_state failed: {e}")


def state_key(session_id: str, transcript_path: str) -> str:
    """Generate a stable state key for a session/transcript pair."""
    raw = f"{session_id}::{transcript_path}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_hook_payload() -> Dict[str, Any]:
    """Read the structured Claude hook payload from stdin."""
    try:
        data = sys.stdin.read()
        if not data.strip():
            return {}
        payload = json.loads(data)
        debug(f"Hook payload raw={json.dumps(payload, ensure_ascii=False, sort_keys=True)}")
        return payload
    except Exception:
        return {}


def extract_session_and_transcript(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[Path]]:
    """Extract session id and transcript path from a hook payload."""
    session_id = (
        payload.get("sessionId")
        or payload.get("session_id")
        or payload.get("session", {}).get("id")
    )

    transcript = (
        payload.get("transcriptPath")
        or payload.get("transcript_path")
        or payload.get("transcript", {}).get("path")
    )

    if transcript:
        try:
            transcript_path = Path(transcript).expanduser().resolve()
        except Exception:
            transcript_path = None
    else:
        transcript_path = None

    return session_id, transcript_path


def get_content(msg: Dict[str, Any]) -> Any:
    """Return transcript content payload for a message."""
    if not isinstance(msg, dict):
        return None
    if "message" in msg and isinstance(msg.get("message"), dict):
        return msg["message"].get("content")
    return msg.get("content")


def get_role(msg: Dict[str, Any]) -> Optional[str]:
    """Return user/assistant role for a transcript message."""
    t = msg.get("type")
    if t in ("user", "assistant"):
        return t
    m = msg.get("message")
    if isinstance(m, dict):
        r = m.get("role")
        if r in ("user", "assistant"):
            return r
    return None


def is_tool_result(msg: Dict[str, Any]) -> bool:
    """Whether this transcript row is a tool_result container."""
    role = get_role(msg)
    if role != "user":
        return False
    content = get_content(msg)
    if isinstance(content, list):
        return any(isinstance(x, dict) and x.get("type") == "tool_result" for x in content)
    return False


def iter_tool_results(content: Any) -> List[Dict[str, Any]]:
    """Iterate tool_result blocks from a content payload."""
    out: List[Dict[str, Any]] = []
    if isinstance(content, list):
        for x in content:
            if isinstance(x, dict) and x.get("type") == "tool_result":
                out.append(x)
    return out


def iter_tool_uses(content: Any) -> List[Dict[str, Any]]:
    """Iterate tool_use blocks from a content payload."""
    out: List[Dict[str, Any]] = []
    if isinstance(content, list):
        for x in content:
            if isinstance(x, dict) and x.get("type") == "tool_use":
                out.append(x)
    return out


def extract_text(content: Any) -> str:
    """Extract plaintext content from Claude content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for x in content:
            if isinstance(x, dict) and x.get("type") == "text":
                parts.append(x.get("text", ""))
            elif isinstance(x, str):
                parts.append(x)
        return "\n".join([p for p in parts if p])
    return ""


def truncate_text(s: str, max_chars: Optional[int] = None) -> Tuple[str, Dict[str, Any]]:
    """Truncate long text while keeping length/hash metadata."""
    if max_chars is None:
        max_chars = CONFIG.max_chars
    if s is None:
        return "", {"truncated": False, "orig_len": 0}
    orig_len = len(s)
    if orig_len <= max_chars:
        return s, {"truncated": False, "orig_len": orig_len}
    head = s[:max_chars]
    return head, {
        "truncated": True,
        "orig_len": orig_len,
        "kept_len": len(head),
        "sha256": hashlib.sha256(s.encode("utf-8")).hexdigest(),
    }


def get_model(msg: Dict[str, Any]) -> str:
    """Return the model name used by an assistant message."""
    m = msg.get("message")
    if isinstance(m, dict):
        return m.get("model") or "claude"
    return "claude"


def get_message_id(msg: Dict[str, Any]) -> Optional[str]:
    """Return assistant message id when present."""
    m = msg.get("message")
    if isinstance(m, dict):
        mid = m.get("id")
        if isinstance(mid, str) and mid:
            return mid
    return None


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse Claude transcript ISO timestamps into timezone-aware datetimes."""
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def get_msg_timestamp(msg: Dict[str, Any]) -> Optional[datetime]:
    """Return the top-level transcript timestamp."""
    if not isinstance(msg, dict):
        return None
    return parse_timestamp(msg.get("timestamp"))


def get_usage_details(msg: Dict[str, Any]) -> Dict[str, int]:
    """Extract Langfuse-compatible usage counters from an assistant message."""
    usage_details: Dict[str, int] = {}
    message = msg.get("message")
    if not isinstance(message, dict):
        return usage_details
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return usage_details
    key_mapping = {
        "input_tokens": "input",
        "output_tokens": "output",
        "cache_creation_input_tokens": "cache_creation_input",
        "cache_read_input_tokens": "cache_read_input",
    }
    for raw_key, langfuse_key in key_mapping.items():
        value = usage.get(raw_key)
        if isinstance(value, int):
            usage_details[langfuse_key] = value
    return usage_details


def sum_usage_details(messages: List[Dict[str, Any]]) -> Dict[str, int]:
    """Aggregate usage across assistant messages in a turn."""
    totals: Dict[str, int] = {}
    for msg in messages:
        for key, value in get_usage_details(msg).items():
            totals[key] = totals.get(key, 0) + value
    if "input" in totals or "output" in totals:
        totals["total"] = totals.get("input", 0) + totals.get("output", 0)
    return totals


@dataclass
class SessionState:
    """Incremental read state for one transcript."""

    offset: int = 0
    buffer: str = ""
    turn_count: int = 0


def load_session_state(global_state: Dict[str, Any], key: str) -> SessionState:
    """Load persisted state for a specific transcript session."""
    s = global_state.get(key, {})
    return SessionState(
        offset=int(s.get("offset", 0)),
        buffer=str(s.get("buffer", "")),
        turn_count=int(s.get("turn_count", 0)),
    )


def write_session_state(global_state: Dict[str, Any], key: str, ss: SessionState) -> None:
    """Persist state for a specific transcript session."""
    global_state[key] = {
        "offset": ss.offset,
        "buffer": ss.buffer,
        "turn_count": ss.turn_count,
        "updated": datetime.now(timezone.utc).isoformat(),
    }


def read_new_jsonl(transcript_path: Path, ss: SessionState) -> Tuple[List[Dict[str, Any]], SessionState]:
    """Read new transcript rows since the last saved offset."""
    if not transcript_path.exists():
        return [], ss

    try:
        with open(transcript_path, "rb") as f:
            f.seek(ss.offset)
            chunk = f.read()
            new_offset = f.tell()
    except Exception as e:
        debug(f"read_new_jsonl failed: {e}")
        return [], ss

    if not chunk:
        return [], ss

    try:
        text = chunk.decode("utf-8", errors="replace")
    except Exception:
        text = chunk.decode(errors="replace")

    combined = ss.buffer + text
    lines = combined.split("\n")
    ss.buffer = lines[-1]
    ss.offset = new_offset

    msgs: List[Dict[str, Any]] = []
    for line in lines[:-1]:
        line = line.strip()
        if not line:
            continue
        try:
            msgs.append(json.loads(line))
        except Exception:
            continue

    if is_debug_enabled() and msgs:
        for index, msg in enumerate(msgs):
            try:
                debug(f"Transcript msg[{index}] raw={json.dumps(msg, ensure_ascii=False, sort_keys=True)}")
            except Exception:
                debug(f"Transcript msg[{index}] raw=<unserializable>")

    return msgs, ss


@dataclass
class Turn:
    """One user turn with all associated assistant/tool events."""

    user_msg: Dict[str, Any]
    assistant_msgs: List[Dict[str, Any]]
    tool_results_by_id: Dict[str, Any]
    events: List["TurnEvent"]


@dataclass
class TurnEvent:
    """Ordered event within a turn."""

    kind: str
    text: str = ""
    text_meta: Optional[Dict[str, Any]] = None
    tool_id: str = ""
    name: str = ""
    input: Any = None
    output: Optional[str] = None
    output_meta: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


def _normalize_assistant_content(content: Any) -> List[Any]:
    if isinstance(content, list):
        return content
    if content:
        return [{"type": "text", "text": str(content)}]
    return []


def _assistant_events_from_blocks(blocks: List[Any], event_timestamp: Optional[datetime] = None) -> List[TurnEvent]:
    events: List[TurnEvent] = []
    for item in blocks:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text", "")
            if text:
                text_value, text_meta = truncate_text(text)
                events.append(
                    TurnEvent(
                        kind="assistant_text",
                        text=text_value,
                        text_meta=text_meta,
                        timestamp=event_timestamp,
                    )
                )
        elif isinstance(item, dict) and item.get("type") == "tool_use":
            tool_input = item.get("input")
            if not isinstance(tool_input, (dict, list, str, int, float, bool)) and tool_input is not None:
                tool_input = {}
            events.append(
                TurnEvent(
                    kind="tool_call",
                    tool_id=str(item.get("id") or ""),
                    name=item.get("name") or "unknown",
                    input=tool_input,
                    timestamp=event_timestamp,
                )
            )
    return events


def _new_assistant_blocks(previous_blocks: List[Any], current_blocks: List[Any]) -> List[Any]:
    common_prefix_len = 0
    max_prefix = min(len(previous_blocks), len(current_blocks))
    while common_prefix_len < max_prefix and previous_blocks[common_prefix_len] == current_blocks[common_prefix_len]:
        common_prefix_len += 1
    return current_blocks[common_prefix_len:]


def build_turns(messages: List[Dict[str, Any]]) -> List[Turn]:
    """Group transcript rows into ordered user turns."""
    turns: List[Turn] = []
    current_user: Optional[Dict[str, Any]] = None
    assistant_order: List[str] = []
    assistant_latest: Dict[str, Dict[str, Any]] = {}
    assistant_blocks_by_id: Dict[str, List[Any]] = {}
    tool_results_by_id: Dict[str, Any] = {}
    events: List[TurnEvent] = []

    def flush_turn() -> None:
        nonlocal current_user, assistant_order, assistant_latest, assistant_blocks_by_id, tool_results_by_id, events
        if current_user is None or not assistant_latest:
            return
        assistants = [assistant_latest[mid] for mid in assistant_order if mid in assistant_latest]
        turns.append(
            Turn(
                user_msg=current_user,
                assistant_msgs=assistants,
                tool_results_by_id=dict(tool_results_by_id),
                events=list(events),
            )
        )

    for msg in messages:
        role = get_role(msg)

        if is_tool_result(msg):
            for tr in iter_tool_results(get_content(msg)):
                tid = tr.get("tool_use_id")
                if tid:
                    tool_results_by_id[str(tid)] = tr.get("content")
                    out_raw = tr.get("content")
                    out_str = out_raw if isinstance(out_raw, str) else json.dumps(out_raw, ensure_ascii=False)
                    out_trunc, out_meta = truncate_text(out_str)
                    events.append(
                        TurnEvent(
                            kind="tool_result",
                            tool_id=str(tid),
                            output=out_trunc,
                            output_meta=out_meta,
                            timestamp=get_msg_timestamp(msg),
                        )
                    )
            continue

        if role == "user":
            flush_turn()
            current_user = msg
            assistant_order = []
            assistant_latest = {}
            assistant_blocks_by_id = {}
            tool_results_by_id = {}
            events = []
            continue

        if role == "assistant":
            if current_user is None:
                continue

            mid = get_message_id(msg) or f"noid:{len(assistant_order)}"
            if mid not in assistant_latest:
                assistant_order.append(mid)
                assistant_blocks_by_id[mid] = []
            assistant_latest[mid] = msg
            current_blocks = _normalize_assistant_content(get_content(msg))
            previous_blocks = assistant_blocks_by_id.get(mid, [])
            new_blocks = _new_assistant_blocks(previous_blocks, current_blocks)
            assistant_blocks_by_id[mid] = current_blocks
            events.extend(_assistant_events_from_blocks(new_blocks, event_timestamp=get_msg_timestamp(msg)))
            continue

    flush_turn()
    return turns
