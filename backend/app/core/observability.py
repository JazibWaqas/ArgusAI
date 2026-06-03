from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from .config import settings


_tracer: Optional[Any] = None
_tracing_error: Optional[str] = None

# OpenInference semantic-convention keys. Phoenix reads these to classify spans
# (LLM / TOOL / CHAIN), render inputs and outputs, and compute token usage and
# cost. Plain OpenTelemetry attributes alone leave every LLM and cost panel empty.
SPAN_KIND = "openinference.span.kind"
INPUT_VALUE = "input.value"
OUTPUT_VALUE = "output.value"
LLM_MODEL_NAME = "llm.model_name"
LLM_PROVIDER = "llm.provider"
LLM_SYSTEM = "llm.system"
LLM_TOKEN_PROMPT = "llm.token_count.prompt"
LLM_TOKEN_COMPLETION = "llm.token_count.completion"
LLM_TOKEN_TOTAL = "llm.token_count.total"
TOOL_NAME = "tool.name"
TOOL_DESCRIPTION = "tool.description"
SESSION_ID = "session.id"


def _status_ok() -> Optional[Any]:
    try:
        from opentelemetry.trace import Status, StatusCode

        return Status(StatusCode.OK)
    except Exception:
        return None


def _status_error(message: str) -> Optional[Any]:
    try:
        from opentelemetry.trace import Status, StatusCode

        return Status(StatusCode.ERROR, message[:300])
    except Exception:
        return None


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
def start_span(
    name: str,
    attributes: Optional[dict[str, Any]] = None,
    kind: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Iterator[Any]:
    tracer = _init_tracer()
    if tracer is None:
        yield NoopSpan()
        return

    with tracer.start_as_current_span(name) as span:
        if kind:
            set_span_attribute(span, SPAN_KIND, kind)
        if session_id:
            set_span_attribute(span, SESSION_ID, session_id)
        for key, value in (attributes or {}).items():
            set_span_attribute(span, key, value)
        try:
            yield span
        except Exception as exc:
            try:
                span.record_exception(exc)
                status = _status_error(str(exc))
                if status is not None:
                    span.set_status(status)
            except Exception:
                pass
            raise
        else:
            try:
                status = _status_ok()
                if status is not None:
                    span.set_status(status)
            except Exception:
                pass


def _truncate(value: Any, limit: int = 4000) -> str:
    text = value if isinstance(value, str) else str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def set_llm_span(
    span: Any,
    *,
    model: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    input_text: Optional[str] = None,
    output_text: Optional[str] = None,
) -> None:
    """Tag a span as an LLM call so Phoenix fills its LLM, token, and cost panels."""
    set_span_attribute(span, SPAN_KIND, "LLM")
    set_span_attribute(span, LLM_SYSTEM, "google")
    set_span_attribute(span, LLM_PROVIDER, "google")
    if model:
        set_span_attribute(span, LLM_MODEL_NAME, model)
    if prompt_tokens is not None:
        set_span_attribute(span, LLM_TOKEN_PROMPT, int(prompt_tokens))
    if completion_tokens is not None:
        set_span_attribute(span, LLM_TOKEN_COMPLETION, int(completion_tokens))
    if total_tokens is not None:
        set_span_attribute(span, LLM_TOKEN_TOTAL, int(total_tokens))
    if input_text:
        set_span_attribute(span, INPUT_VALUE, _truncate(input_text))
    if output_text:
        set_span_attribute(span, OUTPUT_VALUE, _truncate(output_text))


def set_tool_span(
    span: Any,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    input_value: Optional[Any] = None,
    output_value: Optional[Any] = None,
) -> None:
    """Tag a span as a tool call so Phoenix renders it in the Tool spans view."""
    set_span_attribute(span, SPAN_KIND, "TOOL")
    if name:
        set_span_attribute(span, TOOL_NAME, name)
    if description:
        set_span_attribute(span, TOOL_DESCRIPTION, description)
    if input_value is not None:
        set_span_attribute(span, INPUT_VALUE, _truncate(input_value))
    if output_value is not None:
        set_span_attribute(span, OUTPUT_VALUE, _truncate(output_value))


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


def span_id(span: Any) -> Optional[str]:
    try:
        context = span.get_span_context()
        sid = getattr(context, "span_id", 0)
        if sid:
            return f"{int(sid):016x}"
    except Exception:
        return None
    return None


def log_span_annotation(
    span_id_hex: str,
    name: str,
    *,
    label: Optional[str] = None,
    score: Optional[float] = None,
    explanation: Optional[str] = None,
    annotator_kind: str = "HUMAN",
) -> bool:
    """Attach a human or agent evaluation to a span in Phoenix.

    This is what fills the Annotation scores panel and turns confirmed verdicts
    into Phoenix evaluations the reliability agent can later read back. Best
    effort: a failure here never breaks the feedback path.
    """
    base = phoenix_ui_base()
    if not base or not span_id_hex:
        return False
    result: dict[str, Any] = {}
    if label is not None:
        result["label"] = str(label)
    if score is not None:
        result["score"] = float(score)
    if explanation:
        result["explanation"] = _truncate(explanation, 1000)
    if not result:
        return False
    try:
        import httpx

        headers = {"content-type": "application/json"}
        if settings.phoenix_api_key:
            headers["authorization"] = f"Bearer {settings.phoenix_api_key}"
        resp = httpx.post(
            f"{base}/v1/span_annotations?sync=false",
            headers=headers,
            json={
                "data": [
                    {
                        "span_id": span_id_hex,
                        "name": name,
                        "annotator_kind": annotator_kind,
                        "result": result,
                    }
                ]
            },
            timeout=6,
        )
        return resp.status_code < 300
    except Exception:
        return False


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


def get_phoenix_telemetry(limit: int = 500) -> dict[str, Any]:
    """Read behavioral truth from Phoenix: per-detector run counts, error rates,
    and latency, plus LLM token usage and model-fallback rate.

    This is the telemetry the reliability agent fuses with Firestore outcome data.
    Firestore knows whether a detector was *right*; Phoenix knows how it *behaved*
    (slow, erroring, falling back to the cheaper model). Best effort: returns
    ``available: False`` if Phoenix cannot be reached.
    """
    base = phoenix_ui_base()
    project_id = phoenix_project_id()
    empty = {"available": False, "detectors": {}, "llm": {}}
    if not base or not project_id:
        return empty
    try:
        import httpx
        from datetime import datetime

        resp = httpx.get(f"{base}/v1/projects/{project_id}/spans?limit={limit}", timeout=8)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("data", []) or []
    except Exception:
        return empty

    def _latency_s(node: dict[str, Any]) -> Optional[float]:
        try:
            start = node.get("start_time")
            end = node.get("end_time")
            if not start or not end:
                return None
            s = datetime.fromisoformat(start.replace("Z", "+00:00"))
            e = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return max(0.0, (e - s).total_seconds())
        except Exception:
            return None

    detectors: dict[str, dict[str, Any]] = {}
    llm = {"calls": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "models": {}}
    try:
        from .llm import llm_settings

        fallback_model = (llm_settings.gemini_fallback_model or "").strip()
    except Exception:
        fallback_model = ""

    for node in rows:
        kind = (node.get("span_kind") or "").upper()
        attrs = node.get("attributes") or {}
        ok = (node.get("status_code") or "OK").upper() == "OK"
        if kind == "TOOL":
            det = attrs.get("detector.id") or attrs.get("tool.name") or (node.get("name") or "").replace("detector.", "")
            if not det:
                continue
            row = detectors.setdefault(det, {"runs": 0, "errors": 0, "_latency_sum": 0.0, "_latency_n": 0})
            row["runs"] += 1
            if not ok:
                row["errors"] += 1
            lat = attrs.get("detector.latency_seconds")
            if lat is None:
                lat = _latency_s(node)
            if lat is not None:
                row["_latency_sum"] += float(lat)
                row["_latency_n"] += 1
        elif kind == "LLM":
            llm["calls"] += 1
            if not ok:
                llm["errors"] += 1
            pt = int(attrs.get("llm.token_count.prompt") or 0)
            ct = int(attrs.get("llm.token_count.completion") or 0)
            tt = int(attrs.get("llm.token_count.total") or (pt + ct))
            llm["prompt_tokens"] += pt
            llm["completion_tokens"] += ct
            llm["total_tokens"] += tt
            model = attrs.get("llm.model_name") or "unknown"
            m = llm["models"].setdefault(model, {"calls": 0, "tokens": 0})
            m["calls"] += 1
            m["tokens"] += tt

    for det, row in detectors.items():
        n = row.pop("_latency_n", 0)
        row["avg_latency_seconds"] = round(row.pop("_latency_sum", 0.0) / n, 4) if n else None
        row["error_rate"] = round(row["errors"] / row["runs"], 4) if row["runs"] else 0.0

    fallback_calls = int((llm["models"].get(fallback_model, {}) or {}).get("calls", 0)) if fallback_model else 0
    llm["fallback_calls"] = fallback_calls
    llm["fallback_rate"] = round(fallback_calls / llm["calls"], 4) if llm["calls"] else 0.0

    return {"available": True, "detectors": detectors, "llm": llm}


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
