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
    detect_accuracy_drift,
    fallback_stats_from_xray,
    get_agent_actions,
    get_detector_reliability,
    get_similar_past_cases,
    get_stats,
    log_agent_action,
    recalibrate_detector_weight,
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


class RecalibrateDetectorRequest(BaseModel):
    detector_id: str = Field(..., min_length=1, max_length=120)
    multiplier: float = Field(..., ge=0.5, le=1.5)
    reason: str = Field(default="agent_recalibration", max_length=500)


class FactCheckNoteRequest(BaseModel):
    session_id: str | None = None
    verdict: str | None = None
    claim: str | None = None
    evidence_summary: str | None = None


class HumanReviewRequest(BaseModel):
    session_id: str | None = None
    reason: str = Field(..., min_length=1, max_length=1000)
    priority: str = Field(default="normal", max_length=40)

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


@app.get("/agent/tools/detectors/{detector_id}/reliability")
async def agent_tool_detector_reliability(detector_id: str) -> dict:
    return get_detector_reliability(detector_id)


@app.get("/agent/tools/similar-cases")
async def agent_tool_similar_cases(media_type: str = "image", limit: int = 8) -> dict:
    return get_similar_past_cases(media_type=media_type, limit=limit)


@app.get("/agent/tools/accuracy-drift")
async def agent_tool_accuracy_drift(recent_limit: int = 8, min_confirmed: int = 3, threshold: float = 0.2) -> dict:
    return detect_accuracy_drift(recent_limit=recent_limit, min_confirmed=min_confirmed, threshold=threshold)


@app.post("/agent/tools/recalibrate-detector")
async def agent_tool_recalibrate_detector(body: RecalibrateDetectorRequest) -> dict:
    return recalibrate_detector_weight(body.detector_id, body.multiplier, body.reason)


def _session_report_payload(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    data = session_store.get(session_id)
    if not data or not data.last_report:
        return None
    return data.last_report.model_dump(mode="json")


@app.post("/agent/tools/draft-fact-check-note")
async def agent_tool_draft_fact_check_note(body: FactCheckNoteRequest) -> dict:
    report = _session_report_payload(body.session_id)
    verdict = body.verdict or (report or {}).get("verdict") or "inconclusive"
    summary = body.evidence_summary or (report or {}).get("short_summary") or "Evidence summary unavailable."
    trace_id = (report or {}).get("phoenix_trace_id")
    claim = body.claim or "the submitted media authenticity claim"
    note = (
        f"Claim reviewed: {claim}\n"
        f"ArgusAI finding: {verdict}.\n"
        f"Evidence basis: {summary}\n"
        f"Audit trail: {'Phoenix trace ' + trace_id if trace_id else 'Phoenix trace unavailable'}.\n"
        "Recommended action: cite this as an automated forensic screening result and keep human editorial review in the loop."
    )
    log_agent_action(
        "fact_check_note",
        f"Drafted fact-check note ({verdict})",
        {"claim": claim[:200], "verdict": verdict, "phoenix_trace_id": trace_id},
    )
    return {"ok": True, "artifact_type": "fact_check_note", "note": note, "phoenix_trace_id": trace_id}


@app.post("/agent/tools/flag-for-human-review")
async def agent_tool_flag_for_human_review(body: HumanReviewRequest) -> dict:
    record = {
        "session_id": body.session_id,
        "reason": body.reason,
        "priority": body.priority,
        "status": "queued_for_human_review",
    }
    try:
        action_dir = Path("logs/agent_actions")
        action_dir.mkdir(parents=True, exist_ok=True)
        path = action_dir / f"human_review_{abs(hash(json.dumps(record, sort_keys=True))) & 0xffffffff:x}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        record["local_artifact"] = str(path)
    except Exception:
        pass
    log_agent_action(
        "flag_review",
        f"Flagged case for human review ({body.priority})",
        {"reason": (body.reason or "")[:200], "priority": body.priority},
    )
    return {"ok": True, **record}


@app.get("/agent/activity")
async def agent_activity(limit: int = 15) -> dict:
    """Recent autonomous agent actions for the operator console."""
    return {"actions": get_agent_actions(limit)}


@app.post("/agent/investigate")
async def agent_investigate() -> dict:
    """In-app investigator agent: reviews reliability from Firestore + Phoenix health,
    recalibrates any detector that has drifted, and narrates what it did. Triggered from
    the operator console so the agent is driven from the website, not the terminal."""
    steps: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    health = pipeline.health_governor.snapshot()
    link = phoenix_link_info()
    steps.append({
        "tool": "get_arize_health",
        "summary": f"Read Arize/Phoenix health (status: {health.get('status', 'ok')}, project: {link.get('project_name')}).",
    })

    drift = detect_accuracy_drift()
    drift_rows = drift.get("detectors", []) if isinstance(drift, dict) else []
    drifted = [d for d in drift_rows if d.get("drifted")]
    steps.append({
        "tool": "detect_accuracy_drift",
        "summary": f"Checked confirmed-accuracy drift across {len(drift_rows)} detector(s) with enough human feedback; {len(drifted)} drifting.",
    })

    stats = get_stats() or {}
    feedback = stats.get("feedback") or {}
    steps.append({
        "tool": "get_stats",
        "summary": f"Read running intelligence: {int((stats.get('global') or {}).get('total_analyses') or 0)} analyses, {int(feedback.get('total_feedback') or 0)} human-confirmed verdicts.",
    })

    for d in drifted:
        det = d.get("detector_id")
        mult = d.get("suggested_multiplier", 0.75)
        delta_pct = abs(round((d.get("delta") or 0) * 100))
        res = recalibrate_detector_weight(det, mult, reason=f"Recent confirmed accuracy fell {delta_pct}% vs historical")
        if res.get("ok"):
            actions.append({"type": "recalibrate", "detector_id": det, "summary": f"Recalibrated {det} to {res.get('weight_multiplier')}x"})
            steps.append({
                "tool": "recalibrate_detector_weight",
                "summary": f"Recalibrated {det}: {res.get('previous_multiplier')}x -> {res.get('weight_multiplier')}x weight.",
            })

    findings = {
        "phoenix_status": health.get("status", "ok"),
        "total_analyses": int((stats.get("global") or {}).get("total_analyses") or 0),
        "confirmed_feedback": int(feedback.get("total_feedback") or 0),
        "real_world_accuracy": feedback.get("accuracy_rate"),
        "drifted_detectors": [{"id": d.get("detector_id"), "recent": d.get("recent_accuracy"), "historical": d.get("historical_accuracy")} for d in drifted],
        "recalibrations": actions,
    }
    client = LLMClient()
    narration = await client.followup_answer(
        "You are the ArgusAI reliability agent. In 3 to 5 sentences, summarize what you checked across Arize/Phoenix and Firestore, what you found about detector reliability and drift, and what action you took. Plain professional language, no em dashes.",
        "reliability_review",
        findings,
    )
    if not narration:
        if actions:
            names = ", ".join(a["detector_id"] for a in actions)
            narration = (
                f"I reviewed detector reliability against human-confirmed outcomes and Phoenix health. "
                f"{len(drifted)} detector(s) had drifted, so I recalibrated their verdict weight: {names}. "
                "Future verdicts will trust those detectors less until their confirmed accuracy recovers."
            )
        else:
            narration = (
                "I reviewed detector reliability against human-confirmed outcomes and Phoenix health. "
                "No detector has drifted beyond tolerance, so no recalibration was needed. The current weighting stands."
            )

    log_agent_action(
        "review",
        f"Ran reliability review: {len(drift_rows)} detectors checked, {len(actions)} recalibrated",
        {"drifted": len(drifted), "recalibrated": len(actions)},
    )

    return {"ok": True, "steps": steps, "actions": actions, "narration": narration, "drifted": len(drifted)}


def _too_large(contents: bytes) -> bool:
    return len(contents) > settings.max_upload_mb * 1024 * 1024


def _report_verdict(report: Any) -> str:
    verdict = getattr(report, "verdict", "inconclusive")
    return verdict.value if hasattr(verdict, "value") else str(verdict)


def _report_signals(report_payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = report_payload.get("evidence") if isinstance(report_payload.get("evidence"), dict) else {}
    signals = evidence.get("signals") if isinstance(evidence.get("signals"), list) else None
    if signals is None:
        signals = report_payload.get("signals") if isinstance(report_payload.get("signals"), list) else []
    primary = report_payload.get("signal") if isinstance(report_payload.get("signal"), dict) else None
    if primary and not any((s or {}).get("id") == primary.get("id") for s in signals if isinstance(s, dict)):
        signals = [primary, *signals]
    return [s for s in signals if isinstance(s, dict)]


def _find_signal(report_payload: dict[str, Any], detector_id: str | None) -> dict[str, Any] | None:
    signals = _report_signals(report_payload)
    if detector_id:
        needle = detector_id.strip().lower()
        for sig in signals:
            if str(sig.get("id") or "").lower() == needle or str(sig.get("name") or "").lower() == needle:
                return sig
    return max(
        signals,
        key=lambda sig: float(sig.get("verdict_influence_percent") or sig.get("confidence") or 0),
        default=None,
    )


def _investigator_tool_declarations() -> list[dict[str, Any]]:
    return [
        {
            "name": "look_closer_at_media",
            "description": "Inspect the original uploaded image, video, or audio for a focused forensic question without rerunning the full pipeline.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "question": {"type": "STRING", "description": "The focused thing to inspect in the media."}
                },
                "required": ["question"],
            },
        },
        {
            "name": "query_case_history",
            "description": "Query ArgusAI's Firestore history for similar recent cases of the same media type.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "media_type": {"type": "STRING", "description": "image, video, or audio"},
                    "limit": {"type": "NUMBER", "description": "Maximum number of cases to return."},
                },
            },
        },
        {
            "name": "explain_detector_reasoning",
            "description": "Explain why a detector's influence was high or low, including reliability, learned weight, and health-governor context.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "detector_id": {"type": "STRING", "description": "Optional detector id or name from the report."}
                },
            },
        },
        {
            "name": "run_live_provenance",
            "description": "Run live grounded OSINT provenance research on the original media and user's claim.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "claim": {"type": "STRING", "description": "The provenance claim or question to investigate."}
                },
            },
        },
        {
            "name": "draft_fact_check_note",
            "description": "Produce a concise citable fact-check note artifact for this case.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "claim": {"type": "STRING", "description": "The claim being checked."}
                },
            },
        },
        {
            "name": "flag_for_human_review",
            "description": "Flag this case for human review when the evidence is high-impact, uncertain, or contested.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "reason": {"type": "STRING", "description": "Why the case needs human review."},
                    "priority": {"type": "STRING", "description": "low, normal, high, or urgent"},
                },
                "required": ["reason"],
            },
        },
    ]


async def _run_investigator_tool(
    *,
    name: str,
    args: dict[str, Any],
    session_id: str,
    data: Any,
    report_payload: dict[str, Any],
    client: LLMClient,
) -> dict[str, Any]:
    try:
        media_type = str(report_payload.get("media_type") or getattr(data, "media_type", "image") or "image")
        if name == "look_closer_at_media":
            if not data.media_bytes:
                return {"ok": False, "label": "original media unavailable", "error": "The original upload is no longer cached for this session."}
            question = str(args.get("question") or "Look for details relevant to the user's question.")
            result = await client.focused_media_review(data.media_bytes, question, user_context=data.user_context)
            if not result:
                return {"ok": False, "label": f"looked closer at the {media_type}", "error": "Focused media review was unavailable."}
            observations = result.get("observations") if isinstance(result.get("observations"), list) else []
            return {
                "ok": True,
                "label": f"looked closer at the {media_type}",
                "answer": result.get("answer"),
                "observations": observations[:6],
                "confidence": result.get("confidence"),
                "media_type": media_type,
            }

        if name == "query_case_history":
            requested = str(args.get("media_type") or media_type or "image")
            limit = int(args.get("limit") or 6)
            result = get_similar_past_cases(media_type=requested, limit=max(1, min(limit, 10)))
            cases = result.get("cases") or result.get("recent_cases") or []
            if not isinstance(cases, list):
                cases = []
            return {
                **result,
                "ok": bool(result.get("ok", True)),
                "label": f"searched case history -> {len(cases)} matches",
                "cases": cases[:10],
            }

        if name == "explain_detector_reasoning":
            detector_id = str(args.get("detector_id") or "").strip() or None
            sig = _find_signal(report_payload, detector_id)
            if not sig:
                return {"ok": False, "label": "checked detector influence", "error": "No matching signal was found in this report."}
            detector = str(sig.get("id") or detector_id or "unknown")
            reliability = get_detector_reliability(detector)
            health = (report_payload.get("pipeline_health") or {}).get("detector_governor") or {}
            return {
                "ok": True,
                "label": f"checked {detector} influence",
                "detector_id": detector,
                "signal": {
                    "name": sig.get("name"),
                    "status": sig.get("status"),
                    "supports": sig.get("supports"),
                    "confidence": sig.get("confidence"),
                    "reliability": sig.get("reliability"),
                    "verdict_influence_percent": sig.get("verdict_influence_percent"),
                    "summary": sig.get("summary"),
                    "what_found": sig.get("what_found"),
                    "caveat": sig.get("caveat"),
                },
                "reliability": reliability,
                "health_governor": health,
                "score_breakdown": report_payload.get("score_breakdown"),
            }

        if name == "run_live_provenance":
            if not data.media_bytes:
                return {"ok": False, "label": "live provenance unavailable", "error": "The original upload is no longer cached for this session."}
            claim = str(args.get("claim") or data.user_context or "Investigate the provenance of this media.")
            reverse_matches = await client.reverse_image_search(data.media_bytes, claim)
            result = await client.grounded_osint_research_agent(data.media_bytes, claim, reverse_matches=reverse_matches)
            if not result:
                return {"ok": False, "label": "ran live provenance search", "error": "Grounded provenance search was unavailable."}
            osint, meta = result
            fact_sources = osint.get("fact_check_sources") if isinstance(osint.get("fact_check_sources"), list) else []
            hops = int(osint.get("research_hops") or 1)
            return {
                "ok": True,
                "label": f"ran live provenance search -> {len(fact_sources)} sources",
                "osint": osint,
                "grounding_metadata": {
                    "web_search_queries": meta.get("webSearchQueries") or meta.get("web_search_queries") or [],
                },
                "research_hops": hops,
            }

        if name == "draft_fact_check_note":
            claim = str(args.get("claim") or data.user_context or "the submitted media authenticity claim")
            verdict = str(report_payload.get("verdict") or "inconclusive")
            summary = str(report_payload.get("short_summary") or report_payload.get("explanation") or "Evidence summary unavailable.")
            trace_id = report_payload.get("phoenix_trace_id")
            note = (
                f"Claim reviewed: {claim}\n"
                f"ArgusAI finding: {verdict}.\n"
                f"Evidence basis: {summary}\n"
                f"Audit trail: {'Phoenix trace ' + trace_id if trace_id else 'Trace unavailable'}.\n"
                "Recommended use: cite as automated forensic screening and retain human editorial review for publication decisions."
            )
            log_agent_action(
                "fact_check_note",
                f"Drafted fact-check note ({verdict})",
                {"claim": claim[:200], "verdict": verdict, "session_id": session_id},
            )
            return {"ok": True, "label": "drafted fact-check note", "artifact_type": "fact_check_note", "note": note}

        if name == "flag_for_human_review":
            reason = str(args.get("reason") or "The case needs human review.")
            priority = str(args.get("priority") or "normal")[:40]
            record = {"session_id": session_id, "reason": reason[:1000], "priority": priority, "status": "queued_for_human_review"}
            try:
                action_dir = Path("logs/agent_actions")
                action_dir.mkdir(parents=True, exist_ok=True)
                path = action_dir / f"human_review_{abs(hash(json.dumps(record, sort_keys=True))) & 0xffffffff:x}.json"
                path.write_text(json.dumps(record, indent=2), encoding="utf-8")
                record["local_artifact"] = str(path)
            except Exception:
                pass
            log_agent_action("flag_review", f"Flagged case for human review ({priority})", {"reason": reason[:200], "session_id": session_id})
            return {"ok": True, "label": "flagged for human review", **record}

        return {"ok": False, "label": name.replace("_", " "), "error": "Unknown investigator tool."}
    except Exception as exc:
        log.warning("Investigator tool %s failed: %s", name, exc)
        return {"ok": False, "label": name.replace("_", " "), "error": "Tool failed safely."}


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
    session_store.set_media(
        session_id,
        contents,
        media_type=str(getattr(report, "media_type", "image") or "image"),
        content_type=file.content_type or "",
        filename=file.filename or "",
        user_context=context,
    )
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
    session_store.set_media(
        session_id,
        contents,
        media_type="audio",
        content_type=file.content_type or "",
        filename=file.filename or "",
        user_context=context,
    )

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
    verdict = _report_verdict(data.last_report)

    async def run_tool(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        return await _run_investigator_tool(
            name=tool_name,
            args=tool_args,
            session_id=session_id,
            data=data,
            report_payload=report_payload,
            client=client,
        )

    agent_result = await client.investigator_agent_reply(
        user_message=body.message,
        verdict=verdict,
        report=report_payload,
        history=data.messages,
        tools=_investigator_tool_declarations(),
        tool_runner=run_tool,
    )
    reply = (agent_result or {}).get("reply")
    tool_calls = (agent_result or {}).get("tool_calls") or []
    if not reply:
        evidence_payload = report_payload.get("evidence") or report_payload
        reply = await client.followup_answer(body.message, verdict, evidence_payload)
    if not reply:
        reply = "I could not generate a follow-up answer from the available evidence."

    session_store.append_message(session_id, "assistant", reply, {"kind": "text", "tool_calls": tool_calls})
    return {"reply": reply, "session_id": session_id, "tool_calls": tool_calls}


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
    session_store.set_media(
        sid,
        contents,
        media_type=str(getattr(report, "media_type", "image") or "image"),
        content_type=file.content_type or "",
        filename=file.filename or "",
        user_context=context,
    )
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
