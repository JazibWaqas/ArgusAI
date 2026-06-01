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


def span_trace_id(span: Any) -> Optional[str]:
    try:
        context = span.get_span_context()
        trace_id = getattr(context, "trace_id", 0)
        if trace_id:
            return f"{int(trace_id):032x}"
    except Exception:
        return None
    return None


def phoenix_ui_base() -> str:
    """
    The browser-reachable Phoenix UI origin.

    Prefer an explicit dashboard URL, but fall back to deriving it from the
    collector endpoint (strip the trailing ``/v1/traces``). This guarantees the
    UI base points at the same Phoenix instance that actually received traces —
    so deep-links work whether we are pointed at local Docker or Cloud Run.
    """
    dashboard = (settings.phoenix_dashboard_url or "").strip().rstrip("/")
    collector = (settings.phoenix_collector_endpoint or "").strip()
    collector_base = ""
    if collector:
        collector_base = collector.split("/v1/traces")[0].rstrip("/")
    # If both are set but disagree on host, trust the collector (traces live there).
    if dashboard and collector_base:
        return collector_base if collector_base != dashboard else dashboard
    return dashboard or collector_base


_project_id_cache: Optional[str] = None


def phoenix_project_id() -> Optional[str]:
    """Resolve the internal Phoenix project ID for the configured project name.

    Phoenix deep-links use the project's internal (base64) ID in the path, not
    its name. We resolve it once via the REST API and cache it.
    """
    global _project_id_cache
    if _project_id_cache:
        return _project_id_cache
    base = phoenix_ui_base()
    if not base:
        return None
    target = settings.phoenix_project_name or "default"
    try:
        import httpx

        resp = httpx.get(f"{base}/v1/projects", timeout=6, headers={"accept": "application/json"})
        resp.raise_for_status()
        for row in (resp.json() or {}).get("data", []):
            if row.get("name") == target:
                _project_id_cache = str(row.get("id"))
                return _project_id_cache
    except Exception:
        return None
    return None


def phoenix_link_info() -> dict[str, Any]:
    """Everything the frontend needs to build a working trace deep-link."""
    return {
        "base": phoenix_ui_base(),
        "project_id": phoenix_project_id(),
        "project_name": settings.phoenix_project_name,
    }


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
