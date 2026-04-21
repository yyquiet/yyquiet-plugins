#!/usr/bin/env python3
"""
Langfuse 上报模块。

负责将已构建好的 turn/events 映射为 Langfuse observations。
"""

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from langfuse import Langfuse, propagate_attributes

from collector import (
    Turn,
    extract_text,
    get_content,
    get_model,
    get_msg_timestamp,
    sum_usage_details,
    truncate_text,
)
from langfuse_wrapper import TimedLangfuseWrapper


def emit_turn(langfuse: Langfuse, session_id: str, turn_num: int, turn: Turn, transcript_path: Path) -> None:
    """Emit a single turn to Langfuse with ordered child observations."""
    user_text_raw = extract_text(get_content(turn.user_msg))
    user_text, user_text_meta = truncate_text(user_text_raw)
    model = get_model(turn.assistant_msgs[0])
    tool_count = sum(1 for event in turn.events if event.kind == "tool_call")
    usage_details = sum_usage_details(turn.assistant_msgs)
    timed_langfuse = TimedLangfuseWrapper(langfuse)
    trace_timestamp = get_msg_timestamp(turn.user_msg) or next(
        (event.timestamp for event in turn.events if event.timestamp is not None),
        None,
    )
    trace_end_time = next(
        (event.timestamp for event in reversed(turn.events) if event.timestamp is not None),
        trace_timestamp,
    )
    tool_result_timestamps = {
        event.tool_id: event.timestamp
        for event in turn.events
        if event.kind == "tool_result" and event.tool_id
    }

    final_assistant_text_index = -1
    for index, event in enumerate(turn.events):
        if event.kind == "assistant_text" and event.text:
            final_assistant_text_index = index

    final_assistant_text = ""
    if final_assistant_text_index >= 0:
        final_event = turn.events[final_assistant_text_index]
        final_assistant_text = final_event.text

    with propagate_attributes(
        session_id=session_id,
        trace_name=f"Claude Code - Turn {turn_num}",
        tags=["claude-code"],
    ):
        with timed_langfuse.start_as_current_observation(
            name=f"Claude Code - Turn {turn_num}",
            input={"role": "user", "content": user_text},
            completion_start_time=trace_timestamp,
            start_time=trace_timestamp,
            end_time=trace_end_time,
            metadata={
                "source": "claude-code",
                "session_id": session_id,
                "turn_number": turn_num,
                "transcript_path": str(transcript_path),
                "user_text": user_text_meta,
            },
        ) as trace_span:
            for index, event in enumerate(turn.events):
                if event.kind == "assistant_text":
                    if index == final_assistant_text_index:
                        with timed_langfuse.start_as_current_observation(
                            name="Claude Response",
                            as_type="generation",
                            model=model,
                            input={"role": "user", "content": user_text},
                            output={"role": "assistant", "content": event.text},
                            completion_start_time=event.timestamp,
                            start_time=event.timestamp,
                            end_time=event.timestamp,
                            usage_details=usage_details or None,
                            metadata={
                                "assistant_text": event.text_meta,
                                "tool_count": tool_count,
                                "usage_details": usage_details or None,
                            },
                        ):
                            pass
                    elif event.text:
                        with timed_langfuse.start_as_current_observation(
                            name="Assistant Message",
                            input={"role": "assistant", "content": event.text},
                            completion_start_time=event.timestamp,
                            start_time=event.timestamp,
                            end_time=event.timestamp,
                            metadata={
                                "assistant_text": event.text_meta,
                                "phase": "pre_tool_or_intermediate",
                                "observation_kind": "assistant_text",
                            },
                        ):
                            pass
                elif event.kind == "tool_call":
                    tool_input = event.input
                    if isinstance(tool_input, str):
                        tool_input, input_meta = truncate_text(tool_input)
                    else:
                        input_meta = None
                    tool_output = None
                    tool_output_meta = None
                    if event.tool_id and event.tool_id in turn.tool_results_by_id:
                        out_raw = turn.tool_results_by_id[event.tool_id]
                        out_str = out_raw if isinstance(out_raw, str) else json.dumps(out_raw, ensure_ascii=False)
                        tool_output, tool_output_meta = truncate_text(out_str)

                    tool_end_time = tool_result_timestamps.get(event.tool_id) or event.timestamp

                    with timed_langfuse.start_as_current_observation(
                        name=f"Tool: {event.name}",
                        as_type="tool",
                        input=tool_input,
                        completion_start_time=event.timestamp,
                        start_time=event.timestamp,
                        end_time=tool_end_time,
                        metadata={
                            "tool_name": event.name,
                            "tool_id": event.tool_id,
                            "input_meta": input_meta,
                            "output_meta": tool_output_meta,
                        },
                    ) as tool_obs:
                        tool_obs.update(output=tool_output)
                elif event.kind == "tool_result":
                    with timed_langfuse.start_as_current_observation(
                        name="Tool Result",
                        output=event.output,
                        completion_start_time=event.timestamp,
                        start_time=event.timestamp,
                        end_time=event.timestamp,
                        metadata={
                            "tool_id": event.tool_id,
                            "output_meta": event.output_meta,
                            "observation_kind": "tool_result",
                        },
                    ):
                        pass

            trace_span.update(output={"role": "assistant", "content": final_assistant_text})
