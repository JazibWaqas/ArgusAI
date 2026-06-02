"""
Audio forensic pipeline — thin orchestrator that wraps the audio detector.
Separate from the image/video pipeline to keep the two concerns cleanly isolated.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from ..core.analysis_store import persist_analysis
from ..core.llm_client import LLMClient
from ..core.observability import set_span_attribute, span_trace_id, start_span
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
        sha = _hash_bytes(audio_bytes)

        with start_span(
            "argusai.audio_analysis",
            {"media.type": "audio", "audio.sha256": sha},
        ) as root_span:
            trace_id = span_trace_id(root_span)

            # Voice authenticity model (wav2vec2 / HF) always runs and is always shown.
            model_signal = await analyze_audio(audio_bytes)
            try:
                model_signal.name = "Voice Authenticity Model"
                model_signal.category = "audio"
            except Exception:
                pass

            # Gemini semantic listening runs in parallel and is shown as its own card.
            gemini_signal = await self._gemini_audio_signal(audio_bytes, user_context)

            # The verdict is driven by the stronger of the two acoustic signals.
            primary = (
                gemini_signal
                if (gemini_signal and self._should_use_gemini(model_signal, gemini_signal))
                else model_signal
            )

            # Public-context (OSINT) only runs when the user gives a claim to investigate.
            osint_signal = None
            if (user_context or "").strip():
                osint_signal = await self._osint_audio_signal(audio_bytes, user_context)

            acoustic_signal = await self._acoustic_signal(audio_bytes)

            signals = [model_signal]
            if acoustic_signal is not None:
                signals.append(acoustic_signal)
            if gemini_signal is not None:
                signals.append(gemini_signal)
            if osint_signal is not None:
                signals.append(osint_signal)

            duration = round(time.perf_counter() - global_start, 3)

            verdict = primary.supports.value  # "authentic" | "ai_generated" | "unknown"
            certainty = primary.confidence or 0.5
            confidence_label = (primary.metrics or {}).get("confidence_label", "Guarded")
            inference_source = (primary.metrics or {}).get("inference_source", "unknown")

            if verdict == "ai_generated":
                explanation = (
                    f"Our audio analysis indicates this recording is likely AI-generated. "
                    f"{primary.summary} "
                    f"{'Context provided: ' + user_context if user_context else ''}"
                ).strip()
            elif verdict == "authentic":
                explanation = (
                    f"Our audio analysis indicates this recording contains authentic human speech. "
                    f"{primary.summary} "
                    f"{'Context provided: ' + user_context if user_context else ''}"
                ).strip()
            else:
                explanation = (
                    f"Our audio analysis was inconclusive. {primary.summary}"
                ).strip()

            set_span_attribute(root_span, "verdict", verdict)
            set_span_attribute(root_span, "certainty", round(certainty, 4))
            for sig in signals:
                set_span_attribute(root_span, f"detector.{sig.id}.signal_support", sig.supports.value)
                set_span_attribute(root_span, f"detector.{sig.id}.confidence", sig.confidence)
            set_span_attribute(root_span, "pipeline.latency_seconds", duration)

            report = AudioForensicReport(
                media_type="audio",
                verdict=verdict,
                certainty=round(certainty, 4),
                confidence_label=confidence_label,
                explanation=explanation,
                signal=primary,
                signals=signals,
                inference_source=inference_source,
                pipeline_health={"latency_seconds": duration, "sha256": sha},
                phoenix_trace_id=trace_id,
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
                            "phoenix_trace_id": trace_id,
                            "signal": primary.model_dump(mode="json"),
                            "signals": [s.model_dump(mode="json") for s in signals],
                        },
                        f,
                        indent=2,
                    )
            except Exception:
                pass

            persist_analysis(report)

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
            id="audio_semantic",
            name="Gemini Semantic Listening",
            category="semantic",
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

    async def _osint_audio_signal(self, audio_bytes: bytes, user_context: Optional[str]) -> Optional[EvidenceSignal]:
        """Grounded public-context check for audio. Only runs when the user gives a claim.
        Fully best-effort: any failure returns None and the card is simply not shown."""
        try:
            client = LLMClient()
            result = await client.grounded_osint_investigation(audio_bytes, user_context or "")
        except Exception:
            return None
        if not result:
            return None

        data = (result[0] if isinstance(result, tuple) else result) or {}
        known_deepfake = bool(data.get("known_deepfake"))
        verified_real = bool(data.get("verified_real"))
        context = str(data.get("context") or "").strip() or "No decisive public reporting was found for the claimed speaker or context."

        if known_deepfake:
            supports, reliability, confidence = SignalSupport.AI_GENERATED, 0.8, 0.85
        elif verified_real:
            supports, reliability, confidence = SignalSupport.AUTHENTIC, 0.72, 0.2
        else:
            supports, reliability, confidence = SignalSupport.INCONCLUSIVE, 0.4, 0.5

        return EvidenceSignal(
            id="osint_verification",
            name="Public Context (OSINT)",
            category="forensic",
            status=SignalStatus.OK,
            reliability=reliability,
            summary=context,
            what_checked="Searched public reporting to see whether the claimed speaker, statement, or event is documented, disputed, or flagged as fabricated.",
            what_found=context,
            why_it_matters="Acoustic models tell you how the audio was produced. Public context tells you whether the claim it carries is actually real.",
            caveat="Provenance depends on what is publicly documented. An absence of coverage is not proof either way.",
            observations=[context],
            metrics={"known_deepfake": known_deepfake, "verified_real": verified_real},
            confidence=confidence,
            supports=supports,
            notes="Grounded OSINT audio investigation.",
        )

    async def _acoustic_signal(self, audio_bytes: bytes) -> Optional[EvidenceSignal]:
        """Measured acoustic micro-signature (jitter, shimmer, harmonics, tonality).

        Real vocal folds produce small cycle-to-cycle variation that text-to-speech and
        voice clones tend to smooth out. This is a measured, reproducible signal rather
        than a model's opinion. Fully best-effort: any failure returns None."""
        try:
            return await asyncio.to_thread(self._compute_acoustic_signal, audio_bytes)
        except Exception:
            return None

    def _compute_acoustic_signal(self, audio_bytes: bytes) -> Optional[EvidenceSignal]:
        try:
            import numpy as np
            import librosa
            from ..detectors.audio import _load_audio_mono_16k
        except Exception:
            return None

        try:
            waveform, ok = _load_audio_mono_16k(audio_bytes)
        except Exception:
            return None
        if not ok or waveform is None or len(waveform) < 16000:
            return None

        sr = 16000
        waveform = np.asarray(waveform, dtype=np.float32)[: sr * 12]  # cap at 12s for speed

        try:
            f0, voiced_flag, _ = librosa.pyin(waveform, fmin=70, fmax=400, sr=sr)
            f0v = f0[~np.isnan(f0)] if f0 is not None else np.array([])
            jitter = (
                float(np.mean(np.abs(np.diff(1.0 / f0v))) / np.mean(1.0 / f0v))
                if f0v.size > 3 else None
            )
            rms = librosa.feature.rms(y=waveform)[0]
            rms = rms[rms > 1e-5]
            shimmer = float(np.mean(np.abs(np.diff(rms))) / np.mean(rms)) if rms.size > 3 else None
            flatness = float(np.mean(librosa.feature.spectral_flatness(y=waveform)))
            harm, perc = librosa.effects.hpss(waveform)
            eh, ep = float(np.sum(harm ** 2)), float(np.sum(perc ** 2)) + 1e-9
            hnr = float(10.0 * np.log10(eh / ep)) if eh > 0 else None
            voiced_ratio = float(np.mean(voiced_flag)) if voiced_flag is not None else None
        except Exception:
            return None

        def pct(x):
            return f"{x * 100:.2f}%" if x is not None else "n/a"

        observations = [
            f"Pitch jitter (cycle-to-cycle F0 variation): {pct(jitter)}",
            f"Amplitude shimmer (loudness micro-variation): {pct(shimmer)}",
            f"Spectral flatness (tonality): {flatness:.3f}" + (f" | Harmonic-to-noise ratio: {hnr:.1f} dB" if hnr is not None else ""),
            f"Voiced fraction: {pct(voiced_ratio)}",
            "Real human speech carries small, irregular variation from cycle to cycle. Synthetic and cloned voices are often smoother and more regular than a real vocal tract.",
        ]

        supports = SignalSupport.INCONCLUSIVE
        reliability = 0.3
        summary = "The acoustic micro-signature was measured but did not point strongly either way."

        if jitter is not None and shimmer is not None:
            if jitter < 0.005 and shimmer < 0.03:
                supports = SignalSupport.AI_GENERATED
                reliability = 0.55
                summary = (
                    f"The voice is unnaturally regular (jitter {pct(jitter)}, shimmer {pct(shimmer)}), "
                    "which is more typical of synthesized or cloned speech than a real vocal tract."
                )
            elif jitter > 0.01 and shimmer > 0.05:
                supports = SignalSupport.AUTHENTIC
                reliability = 0.5
                summary = (
                    f"The voice shows natural micro-variation (jitter {pct(jitter)}, shimmer {pct(shimmer)}), "
                    "consistent with real vocal-fold behaviour."
                )

        return EvidenceSignal(
            id="audio_acoustics",
            name="Acoustic Micro-Signature",
            category="spectral",
            status=SignalStatus.OK,
            reliability=reliability,
            summary=summary,
            what_checked="We measured the physical micro-variation of the voice: pitch jitter, amplitude shimmer, harmonic-to-noise ratio, and spectral tonality.",
            what_found=summary,
            why_it_matters="Real vocal folds never repeat a cycle perfectly. Text-to-speech and voice clones tend to be smoother and more regular, so this measured signature is hard for a generator to fake without modelling true vocal physics.",
            caveat="Heavy compression, noise reduction, and short or noisy clips can distort these measurements, so this is weighed with the other audio signals.",
            observations=observations,
            metrics={
                "jitter": jitter,
                "shimmer": shimmer,
                "spectral_flatness": flatness,
                "hnr_db": hnr,
                "voiced_ratio": voiced_ratio,
            },
            supports=supports,
            notes="Measured acoustic micro-signature (librosa).",
        )
