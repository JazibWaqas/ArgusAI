from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from .config import settings


HEALTH_LOG_PATH = Path("logs/arize/detector_health.json")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


class DetectorHealthGovernor:
    """
    Local runtime gate for detector health events that are also sent to Phoenix.

    Phoenix is the audit trail. This file-backed governor is the decision surface:
    when a detector reports a circuit breaker, future analyses treat it as unhealthy
    for a short TTL instead of letting it keep voting silently.
    """

    def __init__(self, path: Path = HEALTH_LOG_PATH) -> None:
        self.path = path
        self.state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"detectors": {}, "events": []}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        except Exception:
            return

    def is_enabled(self) -> bool:
        return settings.arize_health_governor

    def disabled_reason(self, detector_id: str) -> Optional[str]:
        if not self.is_enabled():
            return None
        det = self.state.get("detectors", {}).get(detector_id)
        if not isinstance(det, dict):
            return None
        disabled_until = _parse_dt(det.get("disabled_until"))
        if disabled_until and disabled_until > _now():
            return str(det.get("reason") or "detector_health_event")
        return None

    def record_signal_health(self, detector_id: str, signal_metrics: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not self.is_enabled():
            return None
        if not signal_metrics.get("circuit_breaker"):
            return None

        reason = str(signal_metrics.get("circuit_breaker_reason") or "detector_circuit_breaker")
        disabled_until = _now() + timedelta(hours=max(1, settings.detector_health_ttl_hours))
        event = {
            "detector_id": detector_id,
            "reason": reason,
            "gap_score": signal_metrics.get("gap_score"),
            "recorded_at": _now().isoformat(),
            "disabled_until": disabled_until.isoformat(),
        }
        self.state.setdefault("detectors", {})[detector_id] = event
        self.state.setdefault("events", []).append(event)
        self.state["events"] = self.state["events"][-200:]
        self._save()
        return event

    def snapshot(self) -> dict[str, Any]:
        detectors = {}
        for detector_id, data in (self.state.get("detectors") or {}).items():
            if not isinstance(data, dict):
                continue
            disabled_until = _parse_dt(data.get("disabled_until"))
            active = bool(disabled_until and disabled_until > _now())
            detectors[detector_id] = {
                **data,
                "active": active,
            }
        active_anomalies = [item for item in detectors.values() if item.get("active")]
        return {
            "enabled": self.is_enabled(),
            "status": "anomaly" if active_anomalies else "ok",
            "active_anomaly_count": len(active_anomalies),
            "detectors": detectors,
            "recent_events": (self.state.get("events") or [])[-10:],
        }
