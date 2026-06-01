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

    def spectral_attenuation_factor(self) -> float:
        if not self.is_enabled():
            return 1.0
        calibration = self.state.get("calibration_divergence")
        if not isinstance(calibration, dict):
            return 1.0
        active_until = _parse_dt(calibration.get("active_until"))
        if active_until and active_until > _now():
            return float(calibration.get("attenuation_factor") or 0.5)
        return 1.0

    def record_calibration_observation(self, spectral_support: str, semantic_support: str) -> Optional[dict[str, Any]]:
        if not self.is_enabled():
            return None
        directional = {"authentic", "ai_generated"}
        disagreed = spectral_support in directional and semantic_support in directional and spectral_support != semantic_support

        streak = int(self.state.get("calibration_streak") or 0)
        streak = streak + 1 if disagreed else 0
        self.state["calibration_streak"] = streak
        self.state["last_calibration_observation"] = {
            "spectral_support": spectral_support,
            "semantic_support": semantic_support,
            "disagreed": disagreed,
            "recorded_at": _now().isoformat(),
            "streak": streak,
        }

        if streak < 3:
            self._save()
            return None

        active_until = _now() + timedelta(hours=max(1, settings.detector_health_ttl_hours))
        event = {
            "detector_id": "spectral_artifacts",
            "reason": "calibration_divergence",
            "spectral_support": spectral_support,
            "semantic_support": semantic_support,
            "recorded_at": _now().isoformat(),
            "active_until": active_until.isoformat(),
            "attenuation_factor": 0.5,
        }
        self.state["calibration_divergence"] = event
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
        calibration = self.state.get("calibration_divergence") if isinstance(self.state.get("calibration_divergence"), dict) else {}
        calibration_until = _parse_dt(calibration.get("active_until")) if calibration else None
        calibration_active = bool(calibration_until and calibration_until > _now())
        status = "calibration_alert" if calibration_active else "anomaly" if active_anomalies else "ok"
        return {
            "enabled": self.is_enabled(),
            "status": status,
            "active_anomaly_count": len(active_anomalies),
            "detectors": detectors,
            "calibration_divergence": {**calibration, "active": calibration_active} if calibration else None,
            "spectral_attenuation_factor": self.spectral_attenuation_factor(),
            "last_calibration_observation": self.state.get("last_calibration_observation"),
            "recent_events": (self.state.get("events") or [])[-10:],
        }
