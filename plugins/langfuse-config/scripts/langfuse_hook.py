#!/usr/bin/env python3
"""
Claude Code -> Langfuse Hook 入口脚本。

负责调度数据采集与 Langfuse 上报，兼容复用旧模块的导出接口。
"""

import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from collector import (
    FileLock,
    build_turns,
    debug,
    extract_session_and_transcript,
    info,
    load_session_state,
    load_state,
    read_hook_payload,
    read_new_jsonl,
    refresh_config,
    save_state,
    set_current_session_id,
    state_key,
    write_session_state,
)

try:
    from langfuse import Langfuse
except Exception as e:
    print(f"langfuse import failed: {e}", file=sys.stderr)
    sys.exit(0)

from reporter import emit_turn


def main() -> int:
    """Run one Claude Stop hook invocation end-to-end."""
    start = time.time()
    config = refresh_config()
    set_current_session_id("")
    debug("Hook started")

    if not config.trace_enabled:
        debug("trace not enabled")
        return 0

    public_key = config.public_key
    secret_key = config.secret_key
    host = config.base_url

    if not public_key or not secret_key or not host:
        debug("missing public_key or secret_key or host")
        return 0

    payload = read_hook_payload()
    session_id, transcript_path = extract_session_and_transcript(payload)
    if session_id:
        set_current_session_id(session_id)
    debug("Extract session and transcript")

    if not session_id or not transcript_path:
        debug("Missing session_id or transcript_path from hook payload; exiting.")
        return 0

    if not transcript_path.exists():
        debug(f"Transcript path does not exist: {transcript_path}")
        return 0

    try:
        langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    except Exception as e:
        debug(f"Langfuse init failed: {e}")
        return 0

    try:
        with FileLock(config.get_lock_file()):
            state = load_state()
            key = state_key(session_id, str(transcript_path))
            session_state = load_session_state(state, key)

            messages, session_state = read_new_jsonl(transcript_path, session_state)
            debug(
                f"read_new_jsonl msgs={len(messages)} offset={session_state.offset} "
                f"turn_count={session_state.turn_count}"
            )
            if not messages:
                write_session_state(state, key, session_state)
                save_state(state)
                return 0

            turns = build_turns(messages)
            debug(f"build_turns turns={len(turns)}")
            if not turns:
                write_session_state(state, key, session_state)
                save_state(state)
                return 0

            emitted = 0
            for turn in turns:
                emitted += 1
                turn_num = session_state.turn_count + emitted
                try:
                    emit_turn(langfuse, session_id, turn_num, turn, transcript_path)
                except Exception as e:
                    debug(f"emit_turn failed: {e}")

            session_state.turn_count += emitted
            write_session_state(state, key, session_state)
            save_state(state)

        try:
            langfuse.flush()
        except Exception:
            pass

        duration = time.time() - start
        info(f"Processed {emitted} turns in {duration:.2f}s (session={session_id})")
        return 0
    except Exception as e:
        debug(f"Unexpected failure: {e}")
        return 0
    finally:
        try:
            langfuse.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
