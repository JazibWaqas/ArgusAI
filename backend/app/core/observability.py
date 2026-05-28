from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from .config import settings


_tracer: Optional[Any] = None
_tracing_error: Optional[str] = None


def _init_tracer() -> Optional[Any]:
    global _tracer, _tracing_error
    if _tracer is not None or _tracing_error is not None:
        return _tracer

    try:
        if settings.phoenix_project_name:
            os.environ.setdefault("PHOENIX_PROJECT_NAME", settings.phoenix_project_name)
        if settings.phoenix_collector_endpoint:
            os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", settings.phoenix_collector_endpoint)

        from phoenix.otel import register

        register_kwargs: dict[str, Any] = {
            "project_name": settings.phoenix_project_name,
            "auto_instrument": False,
            "batch": False,
        }
        if settings.phoenix_collector_endpoint:
            register_kwargs["endpoint"] = settings.phoenix_collector_endpoint
            register_kwargs["protocol"] = "http/protobuf"
        tracer_provider = register(**register_kwargs)
        _tracer = tracer_provider.get_tracer("argusai.pipeline")
    except Exception as exc:
        _tracing_error = str(exc)
        _tracer = None
    return _tracer


class NoopSpan:
    def set_attribute(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def add_event(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def record_exception(self, *_args: Any, **_kwargs: Any) -> None:
        return None


@contextmanager
def start_span(name: str, attributes: Optional[dict[str, Any]] = None) -> Iterator[Any]:
    tracer = _init_tracer()
    if tracer is None:
        yield NoopSpan()
        return

    with tracer.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            set_span_attribute(span, key, value)
        yield span


def set_span_attribute(span: Any, key: str, value: Any) -> None:
    if value is None:
        return
    try:
        if isinstance(value, (str, bool, int, float)):
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, str(value))
    except Exception:
        return


def tracing_health() -> dict[str, Any]:
    _init_tracer()
    configured = bool(settings.phoenix_api_key or settings.phoenix_collector_endpoint)
    return {
        "configured": configured,
        "enabled": _tracer is not None,
        "project_name": settings.phoenix_project_name,
        "collector_endpoint": settings.phoenix_collector_endpoint,
        "dashboard_url": settings.phoenix_dashboard_url,
        "error": _tracing_error,
    }
