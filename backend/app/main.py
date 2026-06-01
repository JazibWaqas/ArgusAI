from __future__ import annotations

import logging
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .chat.store import store as session_store
from .core.analysis_store import (
    annotate_phoenix_feedback,
    apply_feedback,
    build_history_context,
    fallback_stats_from_xray,
    get_stats,
    trace_rows_from_firestore,
)
from .core.config import settings
from .core.llm import llm_settings
from .core.llm_client import LLMClient
from .core.observability import phoenix_link_info, tracing_health
from .core.pipeline import AnalysisPipeline
from .core.audio_pipeline import AudioAnalysisPipeline

# Force reloading import
from .detectors.lighting import LightingConsistencyDetector
from .detectors.metadata import MetadataDetector
from .detectors.noise import NoisePatternDetector
from .detectors.registry import registry
from .detectors.semantic import SemanticInconsistencyDetector
from .detectors.ela import ErrorLevelAnalysisDetector
from .detectors.spectral import SpectralArtifactDetector
from .detectors.osint import OpenSourceIntelligenceDetector
from .models.report import ForensicReport
from .models.audio_report import AudioForensicReport

log = logging.getLogger(__name__)

app = FastAPI(title=settings.project_name)
pipeline = AnalysisPipeline()
audio_pipeline = AudioAnalysisPipeline()


@app.on_event("startup")
async def startup_event() -> None:
    """Log startup state.  Audio model warm-up already runs at module import time in detectors/audio.py."""  # noqa: reload
    from .detectors.audio import _local_model, MODEL_LOCAL_DIR
    if _local_model is not None:
        log.info("[startup] Audio detector: local wav2vec2 model ready at '%s'.", MODEL_LOCAL_DIR)
    else:
        log.info("[startup] Audio detector: local model not found — HF Space fallback will be used.")


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)


class AgentChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=8000)


class FeedbackRequest(BaseModel):
    verdict_correct: bool

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _register_detectors() -> None:
    registry.register(SpectralArtifactDetector())
    registry.register(MetadataDetector())
    registry.register(NoisePatternDetector())
    registry.register(LightingConsistencyDetector())
    registry.register(SemanticInconsistencyDetector())
    registry.register(ErrorLevelAnalysisDetector())
    registry.register(OpenSourceIntelligenceDetector())


_register_detectors()


def _sanitize_report_dict_for_pdf(body: dict[str, Any]) -> None:
    """Drop huge metric blobs (ELA image, OSINT grounding) so PDF POST/re-parse stays small and stable."""
    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            for key in ("ela_image_base64", "grounding_metadata", "search_queries"):
                value.pop(key, None)
            for child in list(value.values()):
                scrub(child)
        elif isinstance(value, list):
            for child in value:
                scrub(child)
        return value

    scrub(body)
    ev = body.get("evidence")
    if not isinstance(ev, dict):
        return
    signals = ev.get("signals")
    if not isinstance(signals, list):
        return
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        met = sig.get("metrics")
        if isinstance(met, dict):
            met.pop("ela_image_base64", None)
            met.pop("grounding_metadata", None)
        vip = sig.get("verdict_influence_percent")
        if isinstance(vip, float):
            sig["verdict_influence_percent"] = int(round(max(0.0, min(100.0, vip))))


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "llm_provider_ready": llm_settings.provider_ready(),
        "llm": llm_settings.health_snapshot(),
        "detectors": [detector.id for detector in registry.all()],
        "spectral_model_path": settings.spectral_model_path,
        "spectral_model_exists": os.path.exists(settings.spectral_model_path),
        "arize": tracing_health(),
        "detector_governor": pipeline.health_governor.snapshot(),
    }


@app.get("/arize/health")
async def arize_health() -> dict:
    governor = pipeline.health_governor.snapshot()
    trace = tracing_health()
    if governor.get("status") == "calibration_alert":
        label = "Calibration alert - spectral detector weight reduced"
    elif governor.get("status") == "anomaly":
        label = "Detector anomaly detected - view in Arize"
    elif trace.get("enabled"):
        label = "Monitored by Arize Phoenix"
    elif trace.get("configured"):
        label = "Phoenix configured, waiting for tracer"
    else:
        label = "Phoenix monitor not configured"
    return {
        "status": governor.get("status", "ok"),
        "label": label,
        "dashboard_url": settings.phoenix_dashboard_url,
        "phoenix_link": phoenix_link_info(),
        "tracing": trace,
        "detector_governor": governor,
    }


@app.get("/arize/traces")
async def arize_traces(limit: int = 10) -> dict:
    firestore_rows = trace_rows_from_firestore(limit)
    if firestore_rows:
        return {"traces": firestore_rows, "source": "firestore"}

    log_dir = Path("logs/xray")
    if not log_dir.exists():
        return {"traces": [], "source": "none"}

    traces: list[dict[str, Any]] = []
    for path in sorted(log_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[: max(1, min(limit, 50))]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        detectors = {}
        raw_detectors = data.get("detector_metrics") or {}
        if isinstance(raw_detectors, dict):
            for detector_id, row in raw_detectors.items():
                if not isinstance(row, dict):
                    continue
                detectors[detector_id] = {
                    "status": str(row.get("status") or "unknown").lower(),
                    "latency": row.get("time_seconds"),
                    "support": row.get("support"),
                    "visible": row.get("visible", True),
                }

        signal = data.get("signal")
        if isinstance(signal, dict):
            detectors[signal.get("id") or "audio_deepfake"] = {
                "status": signal.get("status"),
                "latency": (signal.get("metrics") or {}).get("latency_seconds"),
                "support": signal.get("supports"),
                "visible": True,
            }

        health = data.get("pipeline_health") or {}
        governor = health.get("detector_governor") if isinstance(health, dict) else {}
        calibration = governor.get("calibration_divergence") if isinstance(governor, dict) else None
        traces.append(
            {
                "timestamp": data.get("timestamp") or data.get("generated_at"),
                "sha256": data.get("image_hash") or data.get("sha256"),
                "media_type": data.get("media_type") or ("audio" if path.name.startswith("audio_") else "image"),
                "verdict": data.get("final_verdict") or data.get("verdict"),
                "certainty": data.get("certainty"),
                "latency_seconds": data.get("global_execution_time") or data.get("latency_seconds"),
                "phoenix_trace_id": data.get("phoenix_trace_id"),
                "detectors": detectors,
                "circuit_breaker_fired": any(bool((row or {}).get("circuit_breaker")) for row in raw_detectors.values()) if isinstance(raw_detectors, dict) else False,
                "calibration_divergence": bool((calibration or {}).get("active")),
            }
        )

    return {"traces": traces, "source": "xray"}


@app.get("/stats")
async def stats() -> dict:
    firestore_stats = get_stats()
    if firestore_stats:
        return firestore_stats
    return fallback_stats_from_xray()


def _too_large(contents: bytes) -> bool:
    return len(contents) > settings.max_upload_mb * 1024 * 1024


@app.post("/sessions")
async def create_session() -> dict:
    sid = session_store.create()
    return {"session_id": sid}


@app.post("/sessions/{session_id}/analyze")
async def analyze_in_session(
    session_id: str,
    file: UploadFile = File(...),
    context: str = Form(""),
):
    if not session_store.get(session_id):
        return JSONResponse(status_code=404, content={"error": "Unknown session."})
    contents = await file.read()
    if _too_large(contents):
        return JSONResponse(status_code=413, content={"error": "File too large."})

    report = await pipeline.analyze(contents, user_context=context)
    session_store.set_report(session_id, report)
    session_store.append_message(
        session_id,
        "user",
        f"[Analysis request]{(' ' + context) if context.strip() else ''}",
        {"kind": "analyze"},
    )
    session_store.append_message(
        session_id,
        "assistant",
        report.explanation,
        {"kind": "report", "verdict": report.verdict.value, "report": report.model_dump(mode="json")},
    )
    return report.model_dump(mode="json")


@app.post("/sessions/{session_id}/analyze-audio")
async def analyze_audio_in_session(
    session_id: str,
    file: UploadFile = File(...),
    context: str = Form(""),
):
    """
    Analyze an audio file for deepfake / AI-generated speech.
    Uses local wav2vec2 model when available, falls back to HF Space.
    """
    if not session_store.get(session_id):
        return JSONResponse(status_code=404, content={"error": "Unknown session."})

    contents = await file.read()
    if _too_large(contents):
        return JSONResponse(status_code=413, content={"error": "File too large."})

    # Reject obvious non-audio early (best-effort MIME sniff)
    content_type = (file.content_type or "").lower()
    if content_type and not (
        content_type.startswith("audio/")
        or content_type in ("application/octet-stream", "")
    ):
        return JSONResponse(
            status_code=415,
            content={"error": f"Expected audio file, got '{content_type}'."},
        )

    report = await audio_pipeline.analyze(contents, user_context=context)
    session_store.set_report(session_id, report)

    session_store.append_message(
        session_id,
        "user",
        f"[Audio analysis request]{(' ' + context) if context.strip() else ''}",
        {"kind": "analyze_audio"},
    )
    session_store.append_message(
        session_id,
        "assistant",
        report.explanation,
        {"kind": "report", "verdict": report.verdict, "report": report.model_dump(mode="json")},
    )
    return report.model_dump(mode="json")


@app.post("/sessions/{session_id}/messages")
async def session_followup(session_id: str, body: ChatMessageRequest):
    data = session_store.get(session_id)
    if not data:
        return JSONResponse(status_code=404, content={"error": "Unknown session."})
    if not data.last_report:
        return JSONResponse(
            status_code=400,
            content={"error": "Run an analysis first so there is evidence to discuss."},
        )

    session_store.append_message(session_id, "user", body.message, {"kind": "text"})

    client = LLMClient()
    report_payload = data.last_report.model_dump(mode="json")
    evidence_payload = report_payload.get("evidence") or report_payload
    reply = await client.followup_answer(
        body.message,
        data.last_report.verdict.value if hasattr(data.last_report.verdict, "value") else str(data.last_report.verdict),
        evidence_payload,
    )
    if not reply:
        reply = "I could not generate a follow-up answer. Check LLM API keys and try again."

    session_store.append_message(session_id, "assistant", reply, {"kind": "text"})
    return {"reply": reply, "session_id": session_id}


@app.post("/sessions/{session_id}/feedback")
async def session_feedback(session_id: str, body: FeedbackRequest):
    data = session_store.get(session_id)
    if not data or not data.last_report:
        return JSONResponse(status_code=404, content={"error": "Unknown session or no prior analysis."})

    result = apply_feedback(data.last_report, body.verdict_correct)
    if not result.get("ok"):
        return JSONResponse(status_code=503, content={"error": result.get("error") or "Feedback persistence unavailable."})

    await annotate_phoenix_feedback(getattr(data.last_report, "phoenix_trace_id", None), body.verdict_correct)
    return {"status": "ok", "feedback": result.get("feedback"), "session_id": session_id}


@app.post("/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    context: str = Form(""),
):
    contents = await file.read()
    if _too_large(contents):
        return JSONResponse(
            status_code=413,
            content={"error": "File too large."},
        )

    report = await pipeline.analyze(contents, user_context=context)
    return report.model_dump(mode="json")


def _agent_report_summary(report: ForensicReport) -> dict[str, Any]:
    history_context = build_history_context(report)
    signals = sorted(
        report.evidence.signals,
        key=lambda sig: (sig.verdict_influence_percent or 0, sig.reliability),
        reverse=True,
    )
    top_signals = [
        {
            "id": sig.id,
            "name": sig.name,
            "status": sig.status.value,
            "supports": sig.supports.value,
            "summary": sig.summary,
            "verdict_influence_percent": sig.verdict_influence_percent,
            "historical_reliability": history_context.get("detector_reliability", {}).get(sig.id),
        }
        for sig in signals[:3]
    ]
    osint = next((sig for sig in report.evidence.signals if sig.id == "osint_verification"), None)
    return {
        "verdict": report.verdict.value,
        "certainty": report.certainty,
        "confidence_label": report.confidence_label,
        "short_summary": report.short_summary,
        "phoenix_trace_id": report.phoenix_trace_id,
        "history_context": history_context,
        "top_signals": top_signals,
        "osint_summary": {
            "summary": osint.summary if osint else None,
            "what_found": osint.what_found if osint else None,
            "research_hops": (osint.metrics or {}).get("research_hops") if osint else None,
            "earliest_web_appearance": (osint.metrics or {}).get("earliest_web_appearance") if osint else None,
            "fact_check_sources": (osint.metrics or {}).get("fact_check_sources") if osint else [],
        },
        "model_health": report.pipeline_health.get("model_health_label"),
        "arize_health": report.pipeline_health.get("detector_governor"),
    }


@app.post("/agent/analyze")
async def agent_analyze(
    file: UploadFile = File(...),
    context: str = Form(""),
):
    contents = await file.read()
    if _too_large(contents):
        return JSONResponse(status_code=413, content={"error": "File too large."})
    report = await pipeline.analyze(contents, user_context=context)
    sid = session_store.create()
    session_store.set_report(sid, report)
    return {"session_id": sid, **_agent_report_summary(report)}


@app.post("/agent/chat")
async def agent_chat(body: AgentChatRequest):
    data = session_store.get(body.session_id)
    if not data or not data.last_report:
        return JSONResponse(status_code=404, content={"error": "Unknown session or no prior analysis."})
    client = LLMClient()
    report_payload = data.last_report.model_dump(mode="json")
    evidence_payload = report_payload.get("evidence") or {}
    evidence_payload["history_context"] = build_history_context(data.last_report)
    evidence_payload["phoenix_trace_id"] = getattr(data.last_report, "phoenix_trace_id", None)
    reply = await client.followup_answer(
        body.message,
        data.last_report.verdict.value,
        evidence_payload,
    )
    return {"reply": reply or "I could not answer from the available forensic evidence.", "session_id": body.session_id}


@app.get("/sessions/{session_id}/report.pdf")
async def download_session_report_pdf(session_id: str):
    data = session_store.get(session_id)
    if not data or not data.last_report:
        return JSONResponse(
            status_code=404,
            content={"error": "No report for this session. Run analyze first."},
        )
    try:
        from .reports import build_official_forensic_pdf

        pdf_bytes = build_official_forensic_pdf(
            data.last_report,
            reference_id=session_id,
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"error": "Could not generate PDF."},
        )
    short = session_id.replace("-", "")[:8]
    filename = f"argusai-report-{short}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/reports/official.pdf")
async def download_official_pdf_from_payload(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body."})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": "Report JSON must be an object."})
    _sanitize_report_dict_for_pdf(body)
    try:
        report = ForensicReport.model_validate(body)
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "Report payload did not match the forensic schema.", "detail": str(exc)},
        )
    try:
        from .reports import build_official_forensic_pdf

        short = (report.evidence.image.sha256 or "report")[:8]
        pdf_bytes = build_official_forensic_pdf(
            report,
            reference_id=f"sha256:{report.evidence.image.sha256}",
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"error": "Could not generate PDF."},
        )
    filename = f"argusai-report-{short}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
