#!/usr/bin/env python3
"""
Langfuse 包装器：在插件内为 observation 增加 start_time / end_time 支持。

这里有意依赖 Langfuse 4.3.1 的内部实现，因此需要配合锁版本使用。
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional, cast

from langfuse import Langfuse
from langfuse._client.span import LangfuseEmbedding, LangfuseGeneration


def _datetime_to_ns(value: Optional[datetime]) -> Optional[int]:
    """Convert a datetime into OpenTelemetry nanoseconds."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1_000_000_000)


class TimedLangfuseWrapper:
    """Thin wrapper around Langfuse that adds start_time/end_time for observations."""

    def __init__(self, client: Langfuse):
        self._client = client

    @contextmanager
    def start_as_current_observation(
        self,
        *,
        name: str,
        as_type: str = "span",
        input: Optional[Any] = None,
        output: Optional[Any] = None,
        metadata: Optional[Any] = None,
        version: Optional[str] = None,
        level: Optional[str] = None,
        status_message: Optional[str] = None,
        completion_start_time: Optional[datetime] = None,
        model: Optional[str] = None,
        model_parameters: Optional[Dict[str, Any]] = None,
        usage_details: Optional[Dict[str, int]] = None,
        cost_details: Optional[Dict[str, float]] = None,
        prompt: Optional[Any] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Iterator[Any]:
        """Create an observation with explicit timing when SDK internals are available."""
        if not hasattr(self._client, "_otel_tracer") or not hasattr(self._client, "_get_span_class"):
            fallback_client = cast(Any, self._client)
            with fallback_client.start_as_current_observation(  # type: ignore[call-overload]
                name=name,
                as_type=as_type,
                input=input,
                output=output,
                metadata=metadata,
                version=version,
                level=level,
                status_message=status_message,
                completion_start_time=completion_start_time,
                model=model,
                model_parameters=model_parameters,
                usage_details=usage_details,
                cost_details=cost_details,
                prompt=prompt,
            ) as observation:
                yield observation
            return

        internal_client = cast(Any, self._client)
        span_class = internal_client._get_span_class(as_type or "span")
        with internal_client._otel_tracer.start_as_current_span(
            name=name,
            end_on_exit=False,
            start_time=_datetime_to_ns(start_time),
        ) as otel_span:
            common_args = {
                "otel_span": otel_span,
                "langfuse_client": self._client,
                "environment": internal_client._environment,
                "release": internal_client._release,
                "input": input,
                "output": output,
                "metadata": metadata,
                "version": version,
                "level": level,
                "status_message": status_message,
            }

            if span_class in [LangfuseGeneration, LangfuseEmbedding]:
                common_args.update(
                    {
                        "completion_start_time": completion_start_time,
                        "model": model,
                        "model_parameters": model_parameters,
                        "usage_details": usage_details,
                        "cost_details": cost_details,
                        "prompt": prompt,
                    }
                )

            observation_factory = cast(Any, span_class)
            observation = observation_factory(**common_args)
            try:
                yield observation
            finally:
                observation.end(end_time=_datetime_to_ns(end_time))
