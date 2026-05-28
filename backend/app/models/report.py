from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .evidence import EvidenceProfile


class Verdict(str, Enum):
    LIKELY_AUTHENTIC = "likely_authentic"
    LIKELY_AI_GENERATED = "likely_ai_generated"
    INCONCLUSIVE = "inconclusive"


class ScoreBreakdown(BaseModel):
    authentic: float = Field(..., ge=0.0)
    ai_generated: float = Field(..., ge=0.0)
    inconclusive: float = Field(..., ge=0.0)
    total_considered: float = Field(..., ge=0.0)


class ForensicReport(BaseModel):
    verdict: Verdict
    certainty: float = Field(..., ge=0.0, le=1.0)
    confidence_label: str
    leaning: Optional[Verdict] = None
    short_summary: str
    explanation: str
    score_breakdown: ScoreBreakdown
    evidence: EvidenceProfile
    generated_at: datetime

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
