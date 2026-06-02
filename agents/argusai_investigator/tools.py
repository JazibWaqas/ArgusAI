from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("ARGUSAI_API_BASE", "http://127.0.0.1:8000").rstrip("/")


def _json_or_error(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text[:1000]}
    if response.is_success:
        return payload
    return {"ok": False, "status_code": response.status_code, "error": payload}


def _media_kind(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix in {".wav", ".mp3", ".ogg", ".flac", ".m4a"}:
        return "audio"
    if suffix in {".mp4", ".webm", ".mov", ".mkv"}:
        return "video"
    return "image"


def analyze_media(file_path: str, context: str = "") -> dict[str, Any]:
    """Run ArgusAI forensic analysis on a local image, video, or audio file path."""
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        return {"ok": False, "error": f"File not found: {path}"}

    media_kind = _media_kind(str(path))
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    try:
        with httpx.Client(timeout=240.0) as client:
            if media_kind == "audio":
                sid_res = client.post(f"{API_BASE}/sessions")
                sid_payload = _json_or_error(sid_res)
                sid = sid_payload.get("session_id")
                if not sid:
                    return {"ok": False, "error": "Could not create session.", "detail": sid_payload}
                with path.open("rb") as f:
                    res = client.post(
                        f"{API_BASE}/sessions/{sid}/analyze-audio",
                        data={"context": context or ""},
                        files={"file": (path.name, f, mime)},
                    )
                payload = _json_or_error(res)
                payload["session_id"] = sid
                payload["ok"] = bool(res.is_success)
                return payload

            with path.open("rb") as f:
                res = client.post(
                    f"{API_BASE}/agent/analyze",
                    data={"context": context or ""},
                    files={"file": (path.name, f, mime)},
                )
            payload = _json_or_error(res)
            payload["ok"] = bool(res.is_success)
            return payload
    except Exception as exc:
        return {"ok": False, "error": f"ArgusAI backend request failed: {exc}"}


def get_detector_reliability(detector_id: str) -> dict[str, Any]:
    """Read Firestore-backed reliability and applied weight for one detector."""
    try:
        with httpx.Client(timeout=30.0) as client:
            return _json_or_error(client.get(f"{API_BASE}/agent/tools/detectors/{detector_id}/reliability"))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def detect_accuracy_drift(recent_limit: int = 8, min_confirmed: int = 3, threshold: float = 0.2) -> dict[str, Any]:
    """Detect recent-vs-historical confirmed accuracy drift for detectors."""
    try:
        with httpx.Client(timeout=45.0) as client:
            return _json_or_error(
                client.get(
                    f"{API_BASE}/agent/tools/accuracy-drift",
                    params={"recent_limit": recent_limit, "min_confirmed": min_confirmed, "threshold": threshold},
                )
            )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def get_similar_past_cases(media_type: str = "image", limit: int = 8) -> dict[str, Any]:
    """Fetch recent same-media ArgusAI investigations from persistent history."""
    try:
        with httpx.Client(timeout=30.0) as client:
            return _json_or_error(
                client.get(f"{API_BASE}/agent/tools/similar-cases", params={"media_type": media_type, "limit": limit})
            )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def recalibrate_detector_weight(detector_id: str, multiplier: float, reason: str = "agent_recalibration") -> dict[str, Any]:
    """Write a bounded detector weight override that future verdicts consume."""
    try:
        with httpx.Client(timeout=30.0) as client:
            return _json_or_error(
                client.post(
                    f"{API_BASE}/agent/tools/recalibrate-detector",
                    json={"detector_id": detector_id, "multiplier": multiplier, "reason": reason},
                )
            )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def draft_fact_check_note(session_id: str = "", claim: str = "", evidence_summary: str = "", verdict: str = "") -> dict[str, Any]:
    """Create a concise citable fact-check note from the current investigation."""
    try:
        with httpx.Client(timeout=30.0) as client:
            return _json_or_error(
                client.post(
                    f"{API_BASE}/agent/tools/draft-fact-check-note",
                    json={
                        "session_id": session_id or None,
                        "claim": claim or None,
                        "evidence_summary": evidence_summary or None,
                        "verdict": verdict or None,
                    },
                )
            )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def flag_for_human_review(session_id: str = "", reason: str = "Low-confidence forensic case.", priority: str = "normal") -> dict[str, Any]:
    """Create a human-review action artifact when automated evidence is not enough."""
    try:
        with httpx.Client(timeout=30.0) as client:
            return _json_or_error(
                client.post(
                    f"{API_BASE}/agent/tools/flag-for-human-review",
                    json={"session_id": session_id or None, "reason": reason, "priority": priority},
                )
            )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def get_arize_health() -> dict[str, Any]:
    """Read current Phoenix tracing and detector-governor health."""
    try:
        with httpx.Client(timeout=20.0) as client:
            return _json_or_error(client.get(f"{API_BASE}/arize/health"))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def get_recent_argusai_traces(limit: int = 5) -> dict[str, Any]:
    """Read recent persisted ArgusAI trace summaries from the backend admin feed."""
    try:
        with httpx.Client(timeout=30.0) as client:
            return _json_or_error(client.get(f"{API_BASE}/arize/traces", params={"limit": limit}))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
