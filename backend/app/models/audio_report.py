"""Pydantic response model for audio deepfake analysis."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel

from .evidence import EvidenceSignal


class AudioForensicReport(BaseModel):
    media_type: str = "audio"

    verdict: str
    """'authentic' | 'ai_generated' | 'unknown'"""

    certainty: float
    """0.0–1.0 — probability score for the verdict direction."""

    confidence_label: str
    """Human-readable tier: 'Guarded' | 'Moderate' | 'High' | 'Very High'"""

    explanation: str
    """Plain-language explanation for the UI."""

    signal: EvidenceSignal
    """The full EvidenceSignal from the detector (mirrors image signals)."""

    inference_source: str
    """'local_wav2vec2' or 'hf_space' — tells the UI which backend ran."""

    pipeline_health: Dict[str, Any]
    """Latency and other diagnostic metadata."""

    phoenix_trace_id: Optional[str] = None

    generated_at: datetime

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
