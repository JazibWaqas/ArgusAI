from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.llm_client import LLMClient
from ..models.evidence import EvidenceProfile, EvidenceSignal, SignalStatus, SignalSupport
from ..models.report import ScoreBreakdown, Verdict


SIGNAL_IMPORTANCE = {
    "spectral_artifacts": 0.7,
    "metadata_analysis": 0.8,
    "noise_pattern_analysis": 0.65,
    "lighting_consistency": 0.5,
    "semantic_inconsistencies": 0.8,
    "error_level_analysis": 0.35,
    "osint_verification": 0.75,
}

STATUS_FACTOR = {
    SignalStatus.OK: 1.0,
    SignalStatus.WARNING: 0.8,
    SignalStatus.UNAVAILABLE: 0.0,
    SignalStatus.ERROR: 0.0,
}


@dataclass
class ScoredSignal:
    signal: EvidenceSignal
    contribution: float
    bucket: str


@dataclass
class ReasoningOutcome:
    verdict: Verdict
    certainty: float
    confidence_label: str
    leaning: Optional[Verdict]
    short_summary: str
    score_breakdown: ScoreBreakdown
    explanation: str
    summary_payload: Dict[str, Any]
    signal_contributions: Dict[str, float] = field(default_factory=dict)


class ReasoningEngine:
    async def reason(self, evidence: EvidenceProfile) -> ReasoningOutcome:
        scored_signals = [self._score_signal(signal) for signal in evidence.signals]

        authentic_score = sum(item.contribution for item in scored_signals if item.bucket == "authentic")
        ai_score = sum(item.contribution for item in scored_signals if item.bucket == "ai_generated")
        inconclusive_score = sum(item.contribution for item in scored_signals if item.bucket == "inconclusive")
        total_considered = authentic_score + ai_score + inconclusive_score
        directional_total = authentic_score + ai_score
        dominant_score = max(authentic_score, ai_score)
        margin = dominant_score - min(authentic_score, ai_score)
        agreement = margin / directional_total if directional_total else 0.0
        uncertainty_ratio = inconclusive_score / total_considered if total_considered else 0.0
        usable_signal_count = sum(
            1 for signal in evidence.signals if signal.status in {SignalStatus.OK, SignalStatus.WARNING} and signal.reliability > 0
        )
        blocked_signal_count = len(evidence.signals) - usable_signal_count

        leaning = None
        if directional_total >= 0.25 and margin >= 0.08:
            leaning = Verdict.LIKELY_AUTHENTIC if authentic_score >= ai_score else Verdict.LIKELY_AI_GENERATED

        if directional_total < 0.25 or dominant_score < 0.22:
            verdict = Verdict.INCONCLUSIVE
        elif agreement < 0.14:
            verdict = Verdict.INCONCLUSIVE
        elif authentic_score > ai_score:
            verdict = Verdict.LIKELY_AUTHENTIC
        else:
            verdict = Verdict.LIKELY_AI_GENERATED

        certainty = self._compute_certainty(
            dominant_score=dominant_score,
            total_considered=total_considered,
            agreement=agreement,
            uncertainty_ratio=uncertainty_ratio,
            usable_signal_ratio=(usable_signal_count / len(evidence.signals)) if evidence.signals else 0.0,
        )
        confidence_label = self._confidence_label(certainty)

        summary_payload = self._build_summary_payload(
            scored_signals=scored_signals,
            authentic_score=authentic_score,
            ai_score=ai_score,
            inconclusive_score=inconclusive_score,
            total_considered=total_considered,
            verdict=verdict,
            certainty=certainty,
            confidence_label=confidence_label,
            leaning=leaning,
            usable_signal_count=usable_signal_count,
            blocked_signal_count=blocked_signal_count,
        )

        fallback_explanation = self._build_fallback_explanation(summary_payload)

        client = LLMClient()
        llm_explanation = await client.generate_explanation(
            verdict=verdict.value,
            evidence=evidence.model_dump(),
            reasoning_summary=summary_payload,
        )

        return ReasoningOutcome(
            verdict=verdict,
            certainty=certainty,
            confidence_label=confidence_label,
            leaning=leaning,
            short_summary=str(summary_payload["short_summary"]),
            score_breakdown=ScoreBreakdown(
                authentic=round(authentic_score, 3),
                ai_generated=round(ai_score, 3),
                inconclusive=round(inconclusive_score, 3),
                total_considered=round(total_considered, 3),
            ),
            explanation=llm_explanation or fallback_explanation,
            summary_payload=summary_payload,
            signal_contributions={s.signal.id: round(s.contribution, 4) for s in scored_signals},
        )

    def _score_signal(self, signal: EvidenceSignal) -> ScoredSignal:
        importance = SIGNAL_IMPORTANCE.get(signal.id, 0.6)
        status_factor = STATUS_FACTOR.get(signal.status, 0.0)
        base_weight = signal.reliability * importance * status_factor

        if signal.supports == SignalSupport.AUTHENTIC:
            support_confidence = self._directional_confidence(signal)
            return ScoredSignal(signal=signal, contribution=base_weight * support_confidence, bucket="authentic")

        if signal.supports == SignalSupport.AI_GENERATED:
            support_confidence = self._directional_confidence(signal)
            return ScoredSignal(signal=signal, contribution=base_weight * support_confidence, bucket="ai_generated")

        if signal.supports == SignalSupport.INCONCLUSIVE:
            return ScoredSignal(signal=signal, contribution=base_weight * 0.8, bucket="inconclusive")

        if signal.reliability > 0 and status_factor > 0:
            return ScoredSignal(signal=signal, contribution=base_weight * 0.35, bucket="inconclusive")

        return ScoredSignal(signal=signal, contribution=0.0, bucket="neutral")

    def _directional_confidence(self, signal: EvidenceSignal) -> float:
        if signal.confidence is None:
            return 0.75

        raw_confidence = float(signal.confidence)
        if signal.supports == SignalSupport.AUTHENTIC:
            raw_confidence = 1.0 - raw_confidence

        raw_confidence = max(0.0, min(1.0, raw_confidence))
        return 0.45 + (raw_confidence * 0.55)

    def _compute_certainty(
        self,
        *,
        dominant_score: float,
        total_considered: float,
        agreement: float,
        uncertainty_ratio: float,
        usable_signal_ratio: float,
    ) -> float:
        if total_considered <= 0.0:
            return 0.0

        coverage = min(1.0, dominant_score)
        base = 0.18 + (0.55 * agreement) + (0.27 * coverage)
        certainty = base * (1.0 - (0.45 * uncertainty_ratio))
        certainty *= 0.75 + (0.25 * max(0.0, min(1.0, usable_signal_ratio)))
        return round(max(0.0, min(0.99, certainty)), 3)

    def _confidence_label(self, certainty: float) -> str:
        if certainty >= 0.78:
            return "high"
        if certainty >= 0.6:
            return "moderate"
        if certainty >= 0.45:
            return "guarded"
        return "low"

    def _build_summary_payload(
        self,
        *,
        scored_signals: List[ScoredSignal],
        authentic_score: float,
        ai_score: float,
        inconclusive_score: float,
        total_considered: float,
        verdict: Verdict,
        certainty: float,
        confidence_label: str,
        leaning: Optional[Verdict],
        usable_signal_count: int,
        blocked_signal_count: int,
    ) -> Dict[str, Any]:
        top_authentic = self._serialize_signals(scored_signals, "authentic")
        top_ai = self._serialize_signals(scored_signals, "ai_generated")
        top_inconclusive = self._serialize_signals(scored_signals, "inconclusive")

        short_summary = self._build_short_summary(
            verdict=verdict,
            certainty=certainty,
            leaning=leaning,
            top_authentic=top_authentic,
            top_ai=top_ai,
            top_inconclusive=top_inconclusive,
        )

        return {
            "verdict": verdict.value,
            "certainty": certainty,
            "certainty_percent": int(round(certainty * 100)),
            "confidence_label": confidence_label,
            "leaning": leaning.value if leaning else None,
            "short_summary": short_summary,
            "scores": {
                "authentic": round(authentic_score, 3),
                "ai_generated": round(ai_score, 3),
                "inconclusive": round(inconclusive_score, 3),
                "total_considered": round(total_considered, 3),
            },
            "signal_coverage": {
                "usable_signal_count": usable_signal_count,
                "blocked_signal_count": blocked_signal_count,
                "total_signal_count": usable_signal_count + blocked_signal_count,
            },
            "top_authentic_signals": top_authentic,
            "top_ai_signals": top_ai,
            "top_inconclusive_signals": top_inconclusive,
        }

    # Generic fallback phrases that the semantic detector emits when it has no
    # specific finding — we detect these so the summary text can be shown instead.
    _SEMANTIC_GENERIC_WHAT_FOUND = (
        "the visual review found visible issues that look more like generation mistakes",
        "the visual review did not find obvious anatomy",
        "the visual review noticed some potentially suspicious details",
        "the visual review did not produce a clear directional result",
        # New semantic.py fallback strings — also replace these with the Gemini summary
        "the visual check found specific problems in this image that are characteristic",
        "the visual check went through the image carefully and did not find any of the usual tells",
        "the visual check spotted a few things that looked slightly off",
    )

    def _serialize_signals(self, scored_signals: List[ScoredSignal], bucket: str) -> List[Dict[str, Any]]:
        selected = [item for item in scored_signals if item.bucket == bucket and item.contribution > 0]
        selected.sort(key=lambda item: item.contribution, reverse=True)
        output = []
        for item in selected[:3]:
            what_found = item.signal.what_found or ""
            why_it_matters = item.signal.why_it_matters or ""

            # If the signal's what_found is a generic semantic placeholder, replace it
            # with the actual Gemini summary which carries the specific observations.
            is_generic_what_found = any(
                what_found.lower().startswith(p) for p in self._SEMANTIC_GENERIC_WHAT_FOUND
            )
            if is_generic_what_found and item.signal.summary:
                what_found = item.signal.summary

            # Similarly fix why_it_matters for the generic semantic fallback
            generic_why = (
                "when an image shows broken anatomy",
                "a scene that holds together visually",
                "that makes this a mixed signal",
                "this check tries to spot visible problems",
            )
            is_generic_why = any(why_it_matters.lower().startswith(p) for p in generic_why)
            if is_generic_why and item.signal.id == "semantic_inconsistencies":
                if bucket == "ai_generated":
                    why_it_matters = (
                        "The visual review is our most human-readable check. When it finds specific, named problems "
                        "like these, it is strong evidence because these are exactly the kinds of mistakes AI generators make "
                        "that a real camera simply cannot produce."
                    )
                elif bucket == "authentic":
                    why_it_matters = (
                        "The visual review is our most human-readable check. When it finds nothing wrong after looking at "
                        "anatomy, geometry, lighting, and fine text, that is meaningful support for the image being real, "
                        "because AI-generated images almost always slip up in at least one of those areas."
                    )

            output.append(
                {
                    "name": item.signal.name,
                    "summary": item.signal.summary,
                    "what_found": what_found,
                    "why_it_matters": why_it_matters,
                    "caveat": item.signal.caveat,
                    "support": item.signal.supports.value,
                    "contribution": round(item.contribution, 3),
                }
            )
        return output

    def _build_short_summary(
        self,
        *,
        verdict: Verdict,
        certainty: float,
        leaning: Optional[Verdict],
        top_authentic: List[Dict[str, Any]],
        top_ai: List[Dict[str, Any]],
        top_inconclusive: List[Dict[str, Any]],
    ) -> str:
        certainty_pct = int(round(certainty * 100))

        def _top_finding(signals: List[Dict[str, Any]]) -> str:
            """Pull the most specific finding from the top signal for the summary."""
            if not signals:
                return ""
            top = signals[0]
            # Prefer a specific what_found over the summary if it has real content
            finding = top.get("what_found") or top.get("summary") or ""
            # If it is a generic fallback phrase, fall back to the summary instead
            generic_phrases = (
                "the visual review found visible issues",
                "the visual review did not find",
                "the visual review noticed some",
            )
            if any(finding.lower().startswith(p) for p in generic_phrases):
                finding = top.get("summary") or finding
            return finding.rstrip(".")

        if verdict == Verdict.LIKELY_AUTHENTIC:
            top = top_authentic[0] if top_authentic else None
            if top:
                finding = _top_finding(top_authentic)
                return (
                    f"This looks like a real photograph. Our confidence is {certainty_pct}%. "
                    f"The strongest reason: {top['name']} found that {finding.lower() if finding else 'the image holds together physically'}."
                )
            return f"The overall picture leans toward a real photograph at {certainty_pct}% confidence, with no strong AI signals detected."

        if verdict == Verdict.LIKELY_AI_GENERATED:
            top = top_ai[0] if top_ai else None
            if top:
                finding = _top_finding(top_ai)
                return (
                    f"This looks AI-generated. Our confidence is {certainty_pct}%. "
                    f"The strongest reason: {top['name']} found that {finding.lower() if finding else 'the image carries generation artifacts'}."
                )
            return f"The overall picture leans toward AI generation at {certainty_pct}% confidence, with multiple signals pointing the same way."

        if leaning == Verdict.LIKELY_AUTHENTIC:
            top = top_authentic[0] if top_authentic else None
            lean_reason = f" {top['name']} is the main reason it leans real." if top else ""
            return (
                f"The result is mixed and we can only say this at {certainty_pct}% confidence. "
                f"More checks point toward authentic than AI, but not by a wide enough margin to be confident.{lean_reason}"
            )

        if leaning == Verdict.LIKELY_AI_GENERATED:
            top = top_ai[0] if top_ai else None
            lean_reason = f" {top['name']} is the main reason it leans AI." if top else ""
            return (
                f"The result is mixed and we can only say this at {certainty_pct}% confidence. "
                f"More checks point toward AI than authentic, but not strongly enough for a firm call.{lean_reason}"
            )

        lead = ", ".join(item["name"] for item in top_inconclusive[:2]) or "multiple checks"
        return (
            f"The checks came back split and we cannot confidently say either way at {certainty_pct}% certainty. "
            f"The most weight came from {lead}, which could not produce a clear direction on their own."
        )

    def _build_fallback_explanation(self, summary: Dict[str, Any]) -> str:
        certainty_percent = summary["certainty_percent"]
        verdict = Verdict(summary["verdict"])
        leaning = summary.get("leaning")
        top_authentic = summary.get("top_authentic_signals", [])
        top_ai = summary.get("top_ai_signals", [])
        top_inconclusive = summary.get("top_inconclusive_signals", [])

        lead_authentic = self._signal_sentence(top_authentic)
        lead_ai = self._signal_sentence(top_ai)
        lead_uncertain = self._signal_sentence(top_inconclusive)

        if verdict == Verdict.LIKELY_AUTHENTIC:
            intro = (
                f"Right now, this looks more like a real photograph than an AI-generated one, with about {certainty_percent}% certainty. "
                "That score reflects how strongly the signals agree, not a guarantee."
            )
            evidence = (
                f"The main reasons are {lead_authentic}. "
                f"We still looked carefully at weaker or mixed signals such as {lead_uncertain}."
            )
            close = "So in plain English, the image holds together more like a camera photo than a generated one, even though no single signal proves that by itself."
            return "\n\n".join([intro, evidence, close])

        if verdict == Verdict.LIKELY_AI_GENERATED:
            intro = (
                f"Right now, this looks more likely AI-generated than camera-captured, with about {certainty_percent}% certainty. "
                "That score reflects how strongly the signals agree, not a guarantee."
            )
            evidence = (
                f"The biggest reasons are {lead_ai}. "
                f"There are still some counter-signals or weaker checks, such as {lead_authentic or lead_uncertain}, but they do not outweigh the main issues."
            )
            close = "So in plain English, more of the stronger signals look like generation artifacts or heavy synthetic processing than like a normal camera photo."
            return "\n\n".join([intro, evidence, close])

        if leaning == Verdict.LIKELY_AUTHENTIC.value:
            lean_text = "slightly toward a real photograph"
            lead_support = lead_authentic
            lead_counter = lead_ai or lead_uncertain
        elif leaning == Verdict.LIKELY_AI_GENERATED.value:
            lean_text = "slightly toward AI generation"
            lead_support = lead_ai
            lead_counter = lead_authentic or lead_uncertain
        else:
            lean_text = "in neither direction strongly enough"
            lead_support = lead_authentic or lead_ai
            lead_counter = lead_ai if lead_authentic else lead_authentic or lead_uncertain

        intro = (
            f"This result is inconclusive, and our current certainty is about {certainty_percent}%. "
            f"The evidence leans {lean_text}, but not strongly enough for a confident final call."
        )
        evidence = (
            f"The main support on one side comes from {lead_support}, while the strongest competing or limiting evidence comes from "
            f"{lead_counter}."
        )
        close = (
            f"Checks such as {lead_uncertain} add even more uncertainty, which is why the right answer here is to explain the balance of evidence instead of forcing a yes-or-no conclusion."
        )
        return "\n\n".join([intro, evidence, close])

    def _signal_sentence(self, items: List[Dict[str, Any]]) -> str:
        if not items:
            return "other weaker signals"

        if len(items) == 1:
            item = items[0]
            detail = item.get("what_found") or item.get("summary") or "it produced a meaningful signal"
            return f"{item['name']}, where we found that {detail.rstrip('.').lower()}."

        first = items[0]
        second = items[1]
        first_detail = first.get("what_found") or first.get("summary") or "it produced a meaningful signal"
        second_detail = second.get("what_found") or second.get("summary") or "it produced a meaningful signal"
        return (
            f"{first['name']}, where we found that {first_detail.rstrip('.').lower()}, "
            f"and {second['name']}, where we found that {second_detail.rstrip('.').lower()}."
        )
