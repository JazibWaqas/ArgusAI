from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from .config import settings
from .firebase import get_db


log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verdict_direction(verdict: Any) -> Optional[str]:
    value = getattr(verdict, "value", verdict)
    text = str(value or "").lower()
    if "ai_generated" in text or text == "ai":
        return "ai_generated"
    if "authentic" in text or text == "real":
        return "authentic"
    return None


def _opposite(direction: Optional[str]) -> Optional[str]:
    if direction == "ai_generated":
        return "authentic"
    if direction == "authentic":
        return "ai_generated"
    return None


# Self-calibration: a detector's verdict weight is nudged by how often it has
# matched human-confirmed ground truth — but only after enough confirmations,
# and within safe bounds, so behaviour stays stable until the data earns a change.
# The confirmation threshold is env-tunable (lower it to demo calibration faster).
LEARNED_WEIGHT_MIN_CONFIRMATIONS = int(os.getenv("LEARNED_WEIGHT_MIN_CONFIRMATIONS", "8"))
LEARNED_WEIGHT_FLOOR = 0.5
LEARNED_WEIGHT_CEIL = 1.5
LEARNED_WEIGHT_BASELINE = 0.6  # confirmed accuracy that maps to a 1.0x multiplier


def _learned_multiplier(confirmed_accuracy: float, confirmed_total: int) -> float:
    if confirmed_total < LEARNED_WEIGHT_MIN_CONFIRMATIONS:
        return 1.0
    raw = confirmed_accuracy / LEARNED_WEIGHT_BASELINE if LEARNED_WEIGHT_BASELINE else 1.0
    return round(max(LEARNED_WEIGHT_FLOOR, min(LEARNED_WEIGHT_CEIL, raw)), 3)


def _bounded_multiplier(value: Any) -> Optional[float]:
    try:
        raw = float(value)
    except Exception:
        return None
    return round(max(LEARNED_WEIGHT_FLOOR, min(LEARNED_WEIGHT_CEIL, raw)), 3)


def _effective_multiplier(data: dict[str, Any]) -> float:
    override = _bounded_multiplier(data.get("agent_weight_override"))
    if override is not None:
        return override
    return _learned_multiplier(
        float(data.get("confirmed_accuracy") or 0.0),
        int(data.get("confirmed_total") or 0),
    )


def _support_direction(support: Any) -> Optional[str]:
    value = getattr(support, "value", support)
    text = str(value or "").lower()
    if text in {"ai_generated", "authentic"}:
        return text
    return None


def _report_sha(report: Any) -> Optional[str]:
    evidence = getattr(report, "evidence", None)
    image = getattr(evidence, "image", None)
    sha = getattr(image, "sha256", None)
    if sha:
        return str(sha)
    health = getattr(report, "pipeline_health", None) or {}
    sha = health.get("sha256") if isinstance(health, dict) else None
    return str(sha) if sha else None


def _report_signals(report: Any) -> list[Any]:
    # Audio reports carry a `signals` list (voice model, semantic, OSINT); prefer it
    # so every audio detector is tracked, not just the primary one.
    direct = getattr(report, "signals", None)
    if direct:
        return list(direct)
    signal = getattr(report, "signal", None)
    if signal is not None:
        return [signal]
    evidence = getattr(report, "evidence", None)
    signals = getattr(evidence, "signals", None)
    return list(signals or [])


def _report_latency(report: Any) -> Optional[float]:
    health = getattr(report, "pipeline_health", None) or {}
    if isinstance(health, dict):
        return health.get("latency_seconds") or health.get("global_execution_time")
    return None


def _signal_latency(signal: Any) -> Optional[float]:
    metrics = getattr(signal, "metrics", None) or {}
    if isinstance(metrics, dict):
        return metrics.get("latency_seconds") or metrics.get("time_seconds")
    return None


def _detector_rows(report: Any, detector_metrics: Optional[dict[str, Any]] = None) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for signal in _report_signals(report):
        detector_id = str(getattr(signal, "id", "") or "")
        if not detector_id:
            continue
        metric_row = (detector_metrics or {}).get(detector_id) if isinstance(detector_metrics, dict) else {}
        metric_row = metric_row if isinstance(metric_row, dict) else {}
        rows[detector_id] = {
            "support": getattr(getattr(signal, "supports", None), "value", getattr(signal, "supports", None)),
            "confidence": getattr(signal, "confidence", None),
            "latency_seconds": metric_row.get("time_seconds") if metric_row.get("time_seconds") is not None else _signal_latency(signal),
            "status": getattr(getattr(signal, "status", None), "value", getattr(signal, "status", None)),
            "visible": getattr(signal, "visible", True),
            "circuit_breaker": bool(metric_row.get("circuit_breaker")),
        }
    return rows


def _global_stats_from_analyses(db: Any, fallback: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Rebuild global counters from persisted analysis docs.

    Firestore transform writes into nested maps can drift by SDK/version and merge
    semantics. The `/analyses` collection is the source of truth for the admin
    console, so read it directly for global counts.
    """
    fallback = fallback or {}
    by_media_type = {"image": 0, "video": 0, "audio": 0}
    by_verdict: dict[str, int] = {}
    total = 0
    last_updated = fallback.get("last_updated")
    try:
        docs = db.collection("analyses").stream()
        for doc in docs:
            data = doc.to_dict() or {}
            total += 1
            media = str(data.get("media_type") or "image").lower()
            by_media_type[media] = by_media_type.get(media, 0) + 1
            verdict = str(data.get("verdict") or "unknown")
            by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
            ts = data.get("timestamp")
            if ts and (not last_updated or str(ts) > str(last_updated)):
                last_updated = ts
    except Exception as exc:
        log.warning("Could not rebuild global stats from analyses: %s", exc)
        return {
            "total_analyses": int(fallback.get("total_analyses") or 0),
            "by_media_type": {"image": 0, "video": 0, "audio": 0, **(fallback.get("by_media_type") or {})},
            "by_verdict": fallback.get("by_verdict") or {},
            "last_updated": fallback.get("last_updated"),
        }
    return {
        "total_analyses": total,
        "by_media_type": by_media_type,
        "by_verdict": by_verdict,
        "last_updated": last_updated,
    }


def build_analysis_record(report: Any, detector_metrics: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    sha = _report_sha(report)
    verdict = getattr(getattr(report, "verdict", None), "value", getattr(report, "verdict", None))
    return {
        "timestamp": getattr(report, "generated_at", datetime.now(timezone.utc)).isoformat(),
        "sha256": sha,
        "media_type": getattr(report, "media_type", "image"),
        "verdict": verdict,
        "certainty": getattr(report, "certainty", None),
        "phoenix_trace_id": getattr(report, "phoenix_trace_id", None),
        "detectors": _detector_rows(report, detector_metrics),
        "latency_seconds": _report_latency(report),
        "user_feedback": None,
        "feedback_timestamp": None,
    }


def _update_detector_stat(db: Any, detector_id: str, row: dict[str, Any], verdict_direction: Optional[str], delta_feedback: int = 0) -> None:
    support = _support_direction(row.get("support"))
    if support not in {"ai_generated", "authentic"}:
        return

    latency = row.get("latency_seconds")
    try:
        latency_val = float(latency) if latency is not None else 0.0
    except Exception:
        latency_val = 0.0

    agrees = bool(verdict_direction and support == verdict_direction)
    doc_ref = db.collection("detector_stats").document(detector_id)

    try:
        from firebase_admin import firestore

        transaction = db.transaction()

        @firestore.transactional
        def update_in_transaction(txn: Any) -> None:
            snap = doc_ref.get(transaction=txn)
            current = snap.to_dict() if snap.exists else {}
            total_runs = int(current.get("total_runs") or 0)
            correct_count = int(current.get("correct_count") or 0)
            avg_latency = float(current.get("avg_latency_seconds") or 0.0)

            if delta_feedback:
                if delta_feedback < 0 and correct_count <= 0:
                    return
                new_correct = max(0, correct_count + delta_feedback)
                new_rate = (new_correct / total_runs) if total_runs else 0.0
                txn.set(
                    doc_ref,
                    {
                        "correct_count": firestore.Increment(delta_feedback),
                        "accuracy_rate": round(new_rate, 4),
                        "last_updated": _now_iso(),
                    },
                    merge=True,
                )
                return

            new_total = total_runs + 1
            correct_delta = 1 if agrees else 0
            new_correct = correct_count + correct_delta
            new_avg = ((avg_latency * total_runs) + latency_val) / new_total
            txn.set(
                doc_ref,
                {
                    "total_runs": firestore.Increment(1),
                    "correct_count": firestore.Increment(correct_delta),
                    "accuracy_rate": round(new_correct / new_total, 4),
                    "avg_latency_seconds": round(new_avg, 4),
                    "last_updated": _now_iso(),
                },
                merge=True,
            )

        update_in_transaction(transaction)
    except Exception as exc:
        log.warning("Could not update detector stat %s: %s", detector_id, exc)


def _record_confirmed(
    db: Any,
    detector_id: str,
    support: Optional[str],
    truth_now: Optional[str],
    truth_prev: Optional[str],
    first_time: bool,
) -> None:
    """Update a detector's human-confirmed accuracy counters.

    ``support`` is what the detector concluded; ``truth_now`` is the human-confirmed
    correct direction. On a first rating we add one confirmation; on a flip we only
    move the correctness delta (the confirmation was already counted).
    """
    if support not in {"ai_generated", "authentic"}:
        return
    correct_now = 1 if support == truth_now else 0
    correct_prev = 1 if (not first_time and support == truth_prev) else 0
    doc_ref = db.collection("detector_stats").document(detector_id)
    try:
        from firebase_admin import firestore

        transaction = db.transaction()

        @firestore.transactional
        def update(txn: Any) -> None:
            snap = doc_ref.get(transaction=txn)
            current = snap.to_dict() if snap.exists else {}
            confirmed_total = int(current.get("confirmed_total") or 0) + (1 if first_time else 0)
            confirmed_correct = int(current.get("confirmed_correct") or 0) + (correct_now - correct_prev)
            confirmed_total = max(0, confirmed_total)
            confirmed_correct = max(0, min(confirmed_total, confirmed_correct))
            txn.set(
                doc_ref,
                {
                    "confirmed_total": confirmed_total,
                    "confirmed_correct": confirmed_correct,
                    "confirmed_accuracy": round(confirmed_correct / confirmed_total, 4) if confirmed_total else 0.0,
                    "last_updated": _now_iso(),
                },
                merge=True,
            )

        update(transaction)
    except Exception as exc:
        log.warning("Could not record confirmed stat %s: %s", detector_id, exc)


def persist_analysis(report: Any, detector_metrics: Optional[dict[str, Any]] = None) -> None:
    db = get_db()
    if db is None:
        return

    record = build_analysis_record(report, detector_metrics)
    sha = record.get("sha256")
    if not sha:
        return

    try:
        db.collection("analyses").document(str(sha)).set(record, merge=True)
    except Exception as exc:
        log.warning("Could not persist analysis %s: %s", sha, exc)
        return

    verdict_direction = _verdict_direction(record.get("verdict"))
    try:
        from firebase_admin import firestore

        media_type = str(record.get("media_type") or "image")
        verdict = str(record.get("verdict") or "inconclusive")
        db.collection("stats").document("global").set(
            {
                "total_analyses": firestore.Increment(1),
                "by_media_type": {media_type: firestore.Increment(1)},
                "by_verdict": {verdict: firestore.Increment(1)},
                "last_updated": _now_iso(),
            },
            merge=True,
        )
    except Exception as exc:
        log.warning("Could not update global stats: %s", exc)

    for detector_id, row in (record.get("detectors") or {}).items():
        _update_detector_stat(db, detector_id, row, verdict_direction)


def get_stats() -> Optional[dict[str, Any]]:
    db = get_db()
    if db is None:
        return None
    try:
        global_doc = db.collection("stats").document("global").get()
        global_stats = global_doc.to_dict() if global_doc.exists else {}
        by_media_type = (global_stats or {}).get("by_media_type") or {}
        by_verdict = (global_stats or {}).get("by_verdict") or {}
        for key, value in (global_stats or {}).items():
            if str(key).startswith("by_media_type."):
                by_media_type[str(key).split(".", 1)[1]] = value
            if str(key).startswith("by_verdict."):
                by_verdict[str(key).split(".", 1)[1]] = value
        global_stats = _global_stats_from_analyses(
            db,
            {
                **(global_stats or {}),
                "by_media_type": by_media_type,
                "by_verdict": by_verdict,
            },
        )
        detectors: dict[str, Any] = {}
        learned_weights: dict[str, Any] = {}
        for doc in db.collection("detector_stats").stream():
            data = doc.to_dict() or {}
            confirmed_total = int(data.get("confirmed_total") or 0)
            confirmed_correct = int(data.get("confirmed_correct") or 0)
            confirmed_accuracy = float(data.get("confirmed_accuracy") or 0.0)
            multiplier = _effective_multiplier(data)
            detectors[doc.id] = {
                "total_runs": int(data.get("total_runs") or 0),
                "correct_count": int(data.get("correct_count") or 0),
                "accuracy_rate": float(data.get("accuracy_rate") or 0.0),
                "confirmed_total": confirmed_total,
                "confirmed_correct": confirmed_correct,
                "confirmed_accuracy": confirmed_accuracy,
                "weight_multiplier": multiplier,
                "agent_weight_override": _bounded_multiplier(data.get("agent_weight_override")),
                "agent_override_reason": data.get("agent_override_reason"),
                "agent_override_updated_at": data.get("agent_override_updated_at"),
                "avg_latency_seconds": float(data.get("avg_latency_seconds") or 0.0),
                "last_updated": data.get("last_updated"),
            }
            if multiplier != 1.0:
                learned_weights[doc.id] = multiplier

        feedback_doc = db.collection("stats").document("feedback").get()
        feedback_raw = feedback_doc.to_dict() if feedback_doc.exists else {}
        confirmed_correct = int((feedback_raw or {}).get("confirmed_correct") or 0)
        confirmed_incorrect = int((feedback_raw or {}).get("confirmed_incorrect") or 0)
        total_feedback = int((feedback_raw or {}).get("total_feedback") or (confirmed_correct + confirmed_incorrect))
        feedback = {
            "confirmed_correct": confirmed_correct,
            "confirmed_incorrect": confirmed_incorrect,
            "total_feedback": total_feedback,
            "accuracy_rate": round(confirmed_correct / total_feedback, 4) if total_feedback else None,
        }

        return {
            "global": {
                "total_analyses": int((global_stats or {}).get("total_analyses") or 0),
                "by_media_type": {"image": 0, "video": 0, "audio": 0, **((global_stats or {}).get("by_media_type") or {})},
                "by_verdict": (global_stats or {}).get("by_verdict") or {},
                "last_updated": (global_stats or {}).get("last_updated"),
            },
            "detectors": detectors,
            "feedback": feedback,
            "learned_weights": learned_weights,
            "source": "firestore",
        }
    except Exception as exc:
        log.warning("Could not read Firestore stats: %s", exc)
        return None


_learned_weights_cache: dict[str, Any] = {"ts": 0.0, "value": {}}
_LEARNED_WEIGHTS_TTL_SECONDS = 60.0


def get_learned_weights() -> dict[str, float]:
    """Per-detector verdict-weight multipliers learned from confirmed accuracy.

    Cached briefly so the verdict engine does not hit Firestore on every analysis.
    Returns an empty dict (no adjustment) when Firebase is unavailable or no
    detector has earned a change yet.
    """
    import time

    now = time.time()
    if now - float(_learned_weights_cache["ts"]) < _LEARNED_WEIGHTS_TTL_SECONDS:
        return _learned_weights_cache["value"]

    stats = get_stats()
    weights = (stats or {}).get("learned_weights") or {}
    _learned_weights_cache["ts"] = now
    _learned_weights_cache["value"] = weights
    return weights


def clear_learned_weights_cache() -> None:
    _learned_weights_cache["ts"] = 0.0
    _learned_weights_cache["value"] = {}


def get_detector_reliability(detector_id: str) -> dict[str, Any]:
    stats = get_stats() or fallback_stats_from_xray()
    detector = ((stats or {}).get("detectors") or {}).get(detector_id)
    if not detector:
        return {
            "ok": False,
            "detector_id": detector_id,
            "error": "Detector reliability not found.",
            "source": (stats or {}).get("source") or "unavailable",
        }
    return {"ok": True, "detector_id": detector_id, "source": stats.get("source"), **detector}


def get_similar_past_cases(media_type: str = "image", limit: int = 8) -> dict[str, Any]:
    rows = trace_rows_from_firestore(max(1, min(limit * 3, 50)))
    source = "firestore"
    if rows is None:
        rows = []
        source = "unavailable"
    media = (media_type or "image").lower()
    cases = [row for row in rows if str(row.get("media_type") or "image").lower() == media][: max(1, min(limit, 20))]
    return {"ok": True, "source": source, "media_type": media, "count": len(cases), "cases": cases}


def detect_accuracy_drift(recent_limit: int = 8, min_confirmed: int = 3, threshold: float = 0.2) -> dict[str, Any]:
    db = get_db()
    if db is None:
        return {"ok": False, "error": "Firebase unavailable.", "detectors": [], "source": "unavailable"}
    recent_n = max(1, min(int(recent_limit or 8), 50))
    min_n = max(1, min(int(min_confirmed or 3), recent_n))
    threshold_val = max(0.01, min(float(threshold or 0.2), 1.0))
    try:
        docs = list(db.collection("analyses").order_by("timestamp", direction="DESCENDING").limit(100).stream())
        per_detector: dict[str, dict[str, Any]] = {}
        for doc in docs:
            data = doc.to_dict() or {}
            feedback = data.get("user_feedback")
            verdict_direction = _verdict_direction(data.get("verdict"))
            if feedback not in {"correct", "incorrect"} or verdict_direction not in {"ai_generated", "authentic"}:
                continue
            truth = verdict_direction if feedback == "correct" else _opposite(verdict_direction)
            detectors = data.get("detectors") if isinstance(data.get("detectors"), dict) else {}
            for detector_id, row in detectors.items():
                if not isinstance(row, dict):
                    continue
                support = _support_direction(row.get("support"))
                if support not in {"ai_generated", "authentic"}:
                    continue
                bucket = per_detector.setdefault(detector_id, {"all": [], "recent": []})
                correct = 1 if support == truth else 0
                bucket["all"].append(correct)
                if len(bucket["recent"]) < recent_n:
                    bucket["recent"].append(correct)

        out = []
        for detector_id, bucket in per_detector.items():
            all_values = bucket["all"]
            recent_values = bucket["recent"]
            if len(recent_values) < min_n or not all_values:
                continue
            historical = sum(all_values) / len(all_values)
            recent = sum(recent_values) / len(recent_values)
            delta = round(recent - historical, 4)
            drifted = delta <= -threshold_val
            out.append(
                {
                    "detector_id": detector_id,
                    "historical_accuracy": round(historical, 4),
                    "recent_accuracy": round(recent, 4),
                    "delta": delta,
                    "recent_confirmations": len(recent_values),
                    "total_confirmations": len(all_values),
                    "drifted": drifted,
                    "suggested_multiplier": 0.75 if drifted else 1.0,
                }
            )
        out.sort(key=lambda row: (not row["drifted"], row["delta"]))
        return {"ok": True, "source": "firestore", "detectors": out, "threshold": threshold_val, "recent_limit": recent_n}
    except Exception as exc:
        log.warning("Could not detect accuracy drift: %s", exc)
        return {"ok": False, "error": "Could not compute drift.", "detectors": [], "source": "firestore"}


def recalibrate_detector_weight(detector_id: str, multiplier: float, reason: str = "agent_recalibration") -> dict[str, Any]:
    db = get_db()
    if db is None:
        return {"ok": False, "error": "Firebase unavailable.", "detector_id": detector_id}
    detector = (detector_id or "").strip()
    if not detector:
        return {"ok": False, "error": "detector_id is required."}
    bounded = _bounded_multiplier(multiplier)
    if bounded is None:
        return {"ok": False, "error": "multiplier must be numeric.", "detector_id": detector}
    try:
        doc_ref = db.collection("detector_stats").document(detector)
        snap = doc_ref.get()
        previous = _effective_multiplier(snap.to_dict() or {}) if snap.exists else 1.0
        doc_ref.set(
            {
                "agent_weight_override": bounded,
                "agent_override_reason": (reason or "agent_recalibration")[:500],
                "agent_override_updated_at": _now_iso(),
                "last_updated": _now_iso(),
            },
            merge=True,
        )
        clear_learned_weights_cache()
        log_agent_action(
            "recalibrate",
            f"Recalibrated {detector}: {previous:.2f}x -> {bounded:.2f}x weight",
            {"detector_id": detector, "previous": previous, "new": bounded, "reason": (reason or "agent_recalibration")[:300]},
        )
        return {
            "ok": True,
            "detector_id": detector,
            "weight_multiplier": bounded,
            "previous_multiplier": previous,
            "reason": (reason or "agent_recalibration")[:500],
        }
    except Exception as exc:
        log.warning("Could not recalibrate detector %s: %s", detector, exc)
        return {"ok": False, "error": "Could not persist recalibration.", "detector_id": detector}


def log_agent_action(action_type: str, summary: str, detail: Optional[dict[str, Any]] = None) -> None:
    """Persist an autonomous agent action so the operator console can show what the
    investigator agent actually did (recalibrations, flags, drafted notes). Best-effort."""
    db = get_db()
    if db is None:
        return
    try:
        db.collection("agent_actions").add(
            {
                "type": action_type,
                "summary": summary[:300],
                "detail": detail or {},
                "timestamp": _now_iso(),
            }
        )
    except Exception as exc:
        log.warning("Could not log agent action %s: %s", action_type, exc)


def get_agent_actions(limit: int = 15) -> list[dict[str, Any]]:
    db = get_db()
    if db is None:
        return []
    try:
        query = db.collection("agent_actions").order_by("timestamp", direction="DESCENDING").limit(max(1, min(limit, 50)))
        return [{"id": doc.id, **(doc.to_dict() or {})} for doc in query.stream()]
    except Exception as exc:
        log.warning("Could not read agent actions: %s", exc)
        return []


def trace_rows_from_firestore(limit: int = 10) -> Optional[list[dict[str, Any]]]:
    db = get_db()
    if db is None:
        return None
    try:
        query = db.collection("analyses").order_by("timestamp", direction="DESCENDING").limit(max(1, min(limit, 50)))
        rows = []
        for doc in query.stream():
            data = doc.to_dict() or {}
            detectors = data.get("detectors") if isinstance(data.get("detectors"), dict) else {}
            rows.append(
                {
                    "timestamp": data.get("timestamp"),
                    "sha256": data.get("sha256") or doc.id,
                    "media_type": data.get("media_type"),
                    "verdict": data.get("verdict"),
                    "certainty": data.get("certainty"),
                    "latency_seconds": data.get("latency_seconds"),
                    "phoenix_trace_id": data.get("phoenix_trace_id"),
                    "detectors": detectors,
                    "circuit_breaker_fired": any(bool((row or {}).get("circuit_breaker")) for row in detectors.values()),
                    "calibration_divergence": False,
                }
            )
        return rows
    except Exception as exc:
        log.warning("Could not query Firestore traces: %s", exc)
        return None


def build_history_context(report: Any, *, limit: int = 25) -> dict[str, Any]:
    stats = get_stats() or fallback_stats_from_xray()
    global_stats = stats.get("global") or {}
    detector_stats = stats.get("detectors") or {}
    media_type = str(getattr(report, "media_type", "image") or "image")

    reliability: dict[str, Any] = {}
    for signal in _report_signals(report):
        detector_id = str(getattr(signal, "id", "") or "")
        if not detector_id:
            continue
        row = detector_stats.get(detector_id) or {}
        total = int(row.get("total_runs") or 0)
        reliability[detector_id] = {
            "signal_name": getattr(signal, "name", detector_id),
            "current_support": getattr(getattr(signal, "supports", None), "value", getattr(signal, "supports", None)),
            "current_confidence": getattr(signal, "confidence", None),
            "total_runs": total,
            "accuracy_rate": float(row.get("accuracy_rate") or 0.0),
            "avg_latency_seconds": float(row.get("avg_latency_seconds") or 0.0),
            "enough_history": total >= 5,
        }

    rows = trace_rows_from_firestore(limit) or []
    same_media = [row for row in rows if (row.get("media_type") or "image") == media_type]
    by_media = global_stats.get("by_media_type") or {}
    same_media_count = int(by_media.get(media_type) or len(same_media) or 0)

    reliable_lines = []
    for detector_id, row in reliability.items():
        if row["enough_history"]:
            reliable_lines.append(
                f"{row['signal_name']} has matched final verdict direction in "
                f"{round(row['accuracy_rate'] * 100)}% of {row['total_runs']} eligible runs"
            )
    summary = (
        f"Firestore has persisted {int(global_stats.get('total_analyses') or 0)} total analyses, "
        f"including {same_media_count} {media_type} investigations."
    )
    if reliable_lines:
        summary += " " + "; ".join(reliable_lines[:4]) + "."

    return {
        "source": stats.get("source") or "unavailable",
        "summary": summary,
        "total_analyses": int(global_stats.get("total_analyses") or 0),
        "same_media_type_analyses": same_media_count,
        "by_media_type": by_media,
        "by_verdict": global_stats.get("by_verdict") or {},
        "detector_reliability": reliability,
        "recent_same_media_cases": [
            {
                "timestamp": row.get("timestamp"),
                "sha256": row.get("sha256"),
                "verdict": row.get("verdict"),
                "certainty": row.get("certainty"),
                "phoenix_trace_id": row.get("phoenix_trace_id"),
            }
            for row in same_media[:5]
        ],
    }


def fallback_stats_from_xray() -> dict[str, Any]:
    log_dir = Path("logs/xray")
    global_stats = {
        "total_analyses": 0,
        "by_media_type": {"image": 0, "video": 0, "audio": 0},
        "by_verdict": {},
    }
    detectors: dict[str, dict[str, Any]] = {}
    empty_feedback = {"confirmed_correct": 0, "confirmed_incorrect": 0, "total_feedback": 0, "accuracy_rate": None}
    if not log_dir.exists():
        return {"global": global_stats, "detectors": detectors, "feedback": empty_feedback, "source": "xray"}

    for path in log_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        global_stats["total_analyses"] += 1
        media = data.get("media_type") or ("audio" if path.name.startswith("audio_") else "image")
        global_stats["by_media_type"][media] = global_stats["by_media_type"].get(media, 0) + 1
        verdict = data.get("final_verdict") or data.get("verdict") or "unknown"
        global_stats["by_verdict"][verdict] = global_stats["by_verdict"].get(verdict, 0) + 1

        raw = data.get("detector_metrics") if isinstance(data.get("detector_metrics"), dict) else {}
        signal = data.get("signal")
        if isinstance(signal, dict):
            raw[signal.get("id") or "audio_deepfake"] = {
                "support": signal.get("supports"),
                "time_seconds": (signal.get("metrics") or {}).get("latency_seconds"),
            }
        verdict_direction = _verdict_direction(verdict)
        for detector_id, row in raw.items():
            if not isinstance(row, dict):
                continue
            support = _support_direction(row.get("support"))
            if support not in {"ai_generated", "authentic"}:
                continue
            item = detectors.setdefault(detector_id, {"total_runs": 0, "correct_count": 0, "_latency_sum": 0.0})
            item["total_runs"] += 1
            item["correct_count"] += 1 if support == verdict_direction else 0
            try:
                item["_latency_sum"] += float(row.get("time_seconds") or 0.0)
            except Exception:
                pass

    for item in detectors.values():
        total = item.get("total_runs") or 0
        item["accuracy_rate"] = round((item.get("correct_count") or 0) / total, 4) if total else 0.0
        item["avg_latency_seconds"] = round((item.pop("_latency_sum", 0.0)) / total, 4) if total else 0.0
    return {"global": global_stats, "detectors": detectors, "feedback": empty_feedback, "source": "xray"}


def apply_feedback(report: Any, verdict_correct: bool) -> dict[str, Any]:
    db = get_db()
    sha = _report_sha(report)
    if not sha:
        return {"ok": False, "error": "Report hash unavailable."}
    if db is None:
        return {"ok": False, "error": "Firebase unavailable."}

    feedback = "correct" if verdict_correct else "incorrect"
    verdict_direction = _verdict_direction(getattr(report, "verdict", None))
    detectors = _detector_rows(report)
    try:
        from firebase_admin import firestore

        doc_ref = db.collection("analyses").document(sha)
        current = doc_ref.get()
        existing = (current.to_dict() or {}).get("user_feedback") if current.exists else None
        doc_ref.set({"user_feedback": feedback, "feedback_timestamp": _now_iso()}, merge=True)
        if existing == feedback:
            return {"ok": True, "feedback": feedback, "unchanged": True}

        # Global real-world accuracy counters (human-confirmed ground truth).
        global_delta: dict[str, Any] = {"last_updated": _now_iso()}
        if existing is None:
            global_delta["total_feedback"] = firestore.Increment(1)
            global_delta["confirmed_correct" if verdict_correct else "confirmed_incorrect"] = firestore.Increment(1)
        else:
            # Flipping an existing rating: move the count between buckets.
            global_delta["confirmed_correct"] = firestore.Increment(1 if verdict_correct else -1)
            global_delta["confirmed_incorrect"] = firestore.Increment(-1 if verdict_correct else 1)
        db.collection("stats").document("feedback").set(global_delta, merge=True)

        # Confirmed-accuracy loop: compare each detector's call to the human-confirmed
        # truth. truth = verdict direction when correct, the opposite when incorrect.
        truth_now = verdict_direction if verdict_correct else _opposite(verdict_direction)
        truth_prev = None if existing is None else (verdict_direction if existing == "correct" else _opposite(verdict_direction))
        first_time = existing is None
        for detector_id, row in detectors.items():
            _record_confirmed(db, detector_id, _support_direction(row.get("support")), truth_now, truth_prev, first_time)
    except Exception as exc:
        log.warning("Could not apply feedback for %s: %s", sha, exc)
        return {"ok": False, "error": "Could not persist feedback."}

    return {"ok": True, "feedback": feedback}


async def annotate_phoenix_feedback(trace_id: Optional[str], verdict_correct: bool) -> None:
    if not trace_id or not settings.phoenix_dashboard_url:
        return
    url = f"{settings.phoenix_dashboard_url.rstrip('/')}/api/v1/evaluations"
    payload = {
        "label": "correct" if verdict_correct else "incorrect",
        "score": 1.0 if verdict_correct else 0.0,
        "trace_id": trace_id,
        "name": "user_verdict_feedback",
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(url, json=payload)
    except Exception:
        return
