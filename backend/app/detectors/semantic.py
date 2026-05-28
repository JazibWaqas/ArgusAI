from __future__ import annotations

import json
from typing import Any, Dict, List

from ..core.llm_client import LLMClient
from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from .base import Detector


class SemanticInconsistencyDetector(Detector):
    id = "semantic_inconsistencies"
    name = "Semantic & Physical Consistency"
    category = "semantic"

    async def analyze(self, image, context: Dict[str, Any]) -> EvidenceSignal:
        image_bytes: bytes = context.get("image_bytes", b"")
        if not image_bytes:
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.UNAVAILABLE,
                reliability=0.0,
                summary="This visual consistency check could not run because the image bytes were missing.",
                what_checked="We look for visible issues such as broken hands, warped geometry, impossible text, or inconsistent reflections.",
                what_found="The semantic detector did not receive the image data it needed.",
                why_it_matters="This check is useful because it can spot visible clues that humans can understand directly.",
                caveat="This is a detector availability issue, not evidence for or against the image.",
                observations=["Image bytes missing in pipeline context."],
                supports=SignalSupport.UNKNOWN,
            )

        client = LLMClient()
        result = await client.analyze_image_semantics(image_bytes)
        if not result:
            observations = ["Set GEMINI_API_KEY to enable semantic analysis."]
            if client.last_error:
                observations.append(client.last_error)
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.UNAVAILABLE,
                reliability=0.0,
                summary="This visual consistency check was unavailable.",
                what_checked="We look for visible issues such as broken hands, warped geometry, impossible text, or inconsistent reflections.",
                what_found="The vision model did not return a usable result.",
                why_it_matters="This check often gives the clearest human-readable clues when an image looks generated.",
                caveat="This only means the detector was unavailable. It is not evidence about the image itself.",
                observations=observations,
                metrics={"provider": client.last_provider, "model": client.last_model, "fallback_used": client.last_fallback_used},
                supports=SignalSupport.UNKNOWN,
            )

        raw_text = result.get("raw_text", "")
        observations: List[str] = []
        confidence = None

        try:
            parsed = json.loads(raw_text)
            anomalies = parsed.get("anomalies", [])
            confidence = parsed.get("confidence")
            summary = parsed.get("summary", "Semantic analysis completed.")
            observations = [str(item) for item in anomalies] if anomalies else ["No obvious semantic anomalies reported."]
        except Exception:
            summary = "The visual review returned text, but not in the expected structure."
            observations = [raw_text[:300]]
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.WARNING,
                reliability=0.15,
                summary=summary,
                what_checked="We looked for visible clues such as anatomy errors, warped shapes, impossible text, or inconsistent lighting/reflections.",
                what_found="The vision model answered, but not in the structured JSON format this detector needs.",
                why_it_matters="That means the semantic detector ran, but its output could not be used reliably.",
                caveat="This is a detector formatting issue rather than evidence for or against authenticity.",
                observations=observations,
                metrics={"provider": client.last_provider, "model": client.last_model, "fallback_used": client.last_fallback_used},
                supports=SignalSupport.UNKNOWN,
                notes="LLM-based semantic reasoning returned unstructured output.",
            )
            
        supports = SignalSupport.UNKNOWN
        final_reliability = 0.4
        what_found = "The visual review did not produce a clear directional result."
        why_it_matters = "This check tries to spot visible problems that often give AI-generated images away."
        caveat = "This detector is useful, but it can still be wrong and should be treated as one part of the full picture."
        
        if confidence is not None:
            if confidence >= 0.65:
                supports = SignalSupport.AI_GENERATED
                what_found = "The visual check found specific problems in this image that are characteristic of AI generation. See the summary above for the exact issues."
                why_it_matters = "When an image has broken anatomy, impossible geometry, or missing shadows, that is strong evidence it was generated rather than photographed."
                if confidence > 0.9:
                    # An explicit reasoning like catching a watermark should override doubt
                    final_reliability = 0.9
                else:
                    final_reliability = 0.55
            elif confidence <= 0.2:
                supports = SignalSupport.AUTHENTIC
                what_found = "The visual check went through the image carefully and did not find any of the usual tells: hands look right, background geometry holds, text is readable, shadows make sense."
                why_it_matters = "AI generators almost always slip up in at least one visible area. Not finding anything here is a meaningful result, not just an absence of evidence."
                final_reliability = 0.3
            else:
                supports = SignalSupport.INCONCLUSIVE
                what_found = "The visual check spotted a few things that looked slightly off, but nothing clear-cut enough to be confident about."
                why_it_matters = "A mixed visual result means we cannot use this check to settle the verdict. The other signals carry more weight here."
                final_reliability = 0.25

        return EvidenceSignal(
            id=self.id,
            name=self.name,
            category=self.category,
            status=SignalStatus.OK,
            reliability=final_reliability,
            summary=summary,
            what_checked="We looked for visible clues such as anatomy errors, warped shapes, impossible text, or inconsistent lighting/reflections.",
            what_found=what_found,
            why_it_matters=why_it_matters,
            caveat=caveat,
            observations=observations,
            metrics={"confidence_raw": confidence, "provider": client.last_provider, "model": client.last_model, "fallback_used": client.last_fallback_used},
            confidence=confidence,
            supports=supports,
            notes="LLM-based semantic reasoning. Treat as advisory evidence.",
        )
