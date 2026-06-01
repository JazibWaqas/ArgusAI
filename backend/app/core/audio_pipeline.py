"""
Audio forensic pipeline — thin orchestrator that wraps the audio detector.
Separate from the image/video pipeline to keep the two concerns cleanly isolated.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from ..core.llm_client import LLMClient
from ..detectors.audio import analyze_audio
from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from ..models.audio_report import AudioForensicReport


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AudioAnalysisPipeline:
    """
    Orchestrates audio deepfake analysis.
    Intentionally minimal — all two-tier logic lives in detectors/audio.py.
    """

    async def analyze(
        self, audio_bytes: bytes, user_context: Optional[str] = None
    ) -> AudioForensicReport:
        global_start = time.perf_counter()

        signal = await analyze_audio(audio_bytes)
        gemini_signal = await self._gemini_audio_signal(audio_bytes, user_context)
        if self._should_use_gemini(signal, gemini_signal):
            signal = gemini_signal

        duration = round(time.perf_counter() - global_start, 3)
        sha = _hash_bytes(audio_bytes)

        # Simple verdict from signal
        verdict = signal.supports.value  # "authentic" | "ai_generated" | "unknown"
        certainty = signal.confidence or 0.5
        confidence_label = (signal.metrics or {}).get("confidence_label", "Guarded")
        inference_source = (signal.metrics or {}).get("inference_source", "unknown")

        if verdict == "ai_generated":
            explanation = (
                f"Our audio analysis indicates this recording is likely AI-generated. "
                f"{signal.summary} "
                f"{'Context provided: ' + user_context if user_context else ''}"
            ).strip()
        elif verdict == "authentic":
            explanation = (
                f"Our audio analysis indicates this recording contains authentic human speech. "
                f"{signal.summary} "
                f"{'Context provided: ' + user_context if user_context else ''}"
            ).strip()
        else:
            explanation = (
                f"Our audio analysis was inconclusive. {signal.summary}"
            ).strip()

        report = AudioForensicReport(
            media_type="audio",
            verdict=verdict,
            certainty=round(certainty, 4),
            confidence_label=confidence_label,
            explanation=explanation,
            signal=signal,
            inference_source=inference_source,
            pipeline_health={"latency_seconds": duration, "sha256": sha},
            generated_at=AudioForensicReport.now(),
        )

        # Write xray log
        try:
            log_dir = Path("logs/xray")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"audio_xray_{sha[:8]}_{int(time.time())}.json"
            with open(log_file, "w") as f:
                json.dump(
                    {
                        "timestamp": report.generated_at.isoformat(),
                        "sha256": sha,
                        "media_type": "audio",
                        "verdict": verdict,
                        "certainty": certainty,
                        "inference_source": inference_source,
                        "latency_seconds": duration,
                        "signal": signal.model_dump(mode="json"),
                    },
                    f,
                    indent=2,
                )
        except Exception:
            pass

        return report

    def _should_use_gemini(self, detector_signal: EvidenceSignal, gemini_signal: Optional[EvidenceSignal]) -> bool:
        if gemini_signal is None or gemini_signal.status != SignalStatus.OK:
            return False
        if gemini_signal.supports == SignalSupport.INCONCLUSIVE:
            return detector_signal.status in {SignalStatus.ERROR, SignalStatus.UNAVAILABLE}
        if detector_signal.status in {SignalStatus.ERROR, SignalStatus.UNAVAILABLE}:
            return True
        if detector_signal.supports in {SignalSupport.INCONCLUSIVE, SignalSupport.UNKNOWN}:
            return True
        detector_conf = detector_signal.confidence or 0.0
        gemini_conf = gemini_signal.confidence or 0.0
        return gemini_conf >= 0.75 and gemini_conf > detector_conf + 0.15

    async def _gemini_audio_signal(self, audio_bytes: bytes, user_context: Optional[str]) -> Optional[EvidenceSignal]:
        client = LLMClient()
        result = await client.analyze_image_semantics(audio_bytes, user_context=user_context or "")
        if not result:
            return None
        raw_text = result.get("raw_text", "")
        try:
            parsed = json.loads(raw_text)
        except Exception:
            return EvidenceSignal(
                id="audio_deepfake",
                name="Gemini Audio Authenticity",
                category="audio",
                status=SignalStatus.WARNING,
                reliability=0.2,
                summary="Gemini reviewed the audio but returned an unstructured response.",
                what_checked="Gemini listened for synthetic speech, cloned-voice artifacts, unnatural cadence, missing breathing, and generated-audio production patterns.",
                what_found=raw_text[:300] if raw_text else "No structured Gemini response was returned.",
                why_it_matters="The Gemini review is useful as a semantic fallback when the specialized audio detector is unavailable or uncertain.",
                caveat="This is a model-based judgment and should be weighed with other evidence when available.",
                observations=[raw_text[:500] if raw_text else "Empty Gemini response."],
                metrics={"provider": client.last_provider, "model": client.last_model, "fallback_used": client.last_fallback_used},
                supports=SignalSupport.UNKNOWN,
            )

        confidence = parsed.get("confidence")
        try:
            confidence = float(confidence)
        except Exception:
            confidence = None
        anomalies = parsed.get("anomalies") if isinstance(parsed.get("anomalies"), list) else []
        summary = str(parsed.get("summary") or "Gemini audio authenticity review completed.")

        supports = SignalSupport.INCONCLUSIVE
        reliability = 0.45
        if confidence is not None and confidence >= 0.60:
            supports = SignalSupport.AI_GENERATED
            reliability = 0.78
        elif confidence is not None and confidence <= 0.20:
            supports = SignalSupport.AUTHENTIC
            reliability = 0.42

        confidence_label = "High" if confidence and confidence >= 0.75 else "Moderate" if confidence and confidence >= 0.60 else "Guarded"
        return EvidenceSignal(
            id="audio_deepfake",
            name="Gemini Audio Authenticity",
            category="audio",
            status=SignalStatus.OK,
            reliability=reliability,
            summary=summary,
            what_checked="Gemini listened for synthetic speech, cloned-voice artifacts, unnatural cadence, missing breathing, and generated-audio production patterns.",
            what_found=summary,
            why_it_matters="When the dedicated wav2vec2 detector is missing or uncertain, Gemini gives the product a direct semantic audio review instead of stopping at an inconclusive model score.",
            caveat="Gemini is an expert semantic judge, not a calibrated audio classifier. Treat this as one evidence signal in the trail.",
            observations=[str(item) for item in anomalies] or ["Gemini did not list specific audio anomalies."],
            metrics={
                "confidence_raw": confidence,
                "confidence_label": confidence_label,
                "inference_source": "gemini_semantic",
                "provider": client.last_provider,
                "model": client.last_model,
                "fallback_used": client.last_fallback_used,
            },
            confidence=confidence,
            supports=supports,
            notes="Gemini semantic audio fallback.",
        )
