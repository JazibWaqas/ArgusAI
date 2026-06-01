from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO
from typing import Any, Dict, List, Optional

from PIL import Image

import time
import json
import os
from pathlib import Path

from ..detectors.registry import registry
from ..core.analysis_store import persist_analysis
from ..core.health_governor import DetectorHealthGovernor
from ..core.llm import llm_settings
from ..core.observability import set_span_attribute, span_trace_id, start_span, tracing_health
from ..models.evidence import EvidenceProfile, ImageInfo
from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from ..models.report import ForensicReport
from ..reasoning.engine import ReasoningEngine


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _looks_like_audio(data: bytes) -> bool:
    return (
        (data.startswith(b"RIFF") and data[8:12] == b"WAVE")
        or data.startswith(b"ID3")
        or data.startswith(b"\xff\xfb")
        or data.startswith(b"\xff\xf3")
        or data.startswith(b"\xff\xf2")
        or data.startswith(b"fLaC")
        or data.startswith(b"OggS")
        or data.startswith(b"\x30\x26\xB2\x75\x8E\x66\xCF\x11")
    )


def _looks_like_video(data: bytes) -> bool:
    header = data[:64]
    return (
        (data.startswith(b"\x00\x00\x00") and b"ftyp" in header and not any(brand in header for brand in (b"M4A", b"M4B", b"m4a", b"m4b")))
        or data.startswith(b"\x1aE\xdf\xa3")
    )


SIGNAL_VISIBILITY = {
    "image": {
        "spectral_artifacts",
        "metadata_analysis",
        "noise_pattern_analysis",
        "lighting_consistency",
        "semantic_inconsistencies",
        "error_level_analysis",
        "osint_verification",
    },
    "video": {
        "spectral_artifacts",
        "metadata_analysis",
        "semantic_inconsistencies",
        "error_level_analysis",
        "osint_verification",
        "temporal_coherence",
        "audio_track",
    },
}


class AnalysisPipeline:
    def __init__(self) -> None:
        self.reasoning = ReasoningEngine()
        self.health_governor = DetectorHealthGovernor()

    async def analyze(self, image_bytes: bytes, user_context: Optional[str] = None) -> ForensicReport:
        global_start = time.perf_counter()
        is_video = False
        is_audio = False
        frames = []
        video_error = None
        
        # Detect audio files by magic bytes
        if _looks_like_audio(image_bytes):
            is_audio = True
            original_format = "AUDIO"
            image = None
        elif _looks_like_video(image_bytes):
            is_video = True
            original_format = "VIDEO"
            image = None
            try:
                import cv2
                from ..core.video import extract_sharpest_frames
                frames_cv = extract_sharpest_frames(image_bytes, max_frames=3)
                image = Image.fromarray(cv2.cvtColor(frames_cv[0], cv2.COLOR_BGR2RGB))
                frames = [Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) for f in frames_cv]
            except Exception as exc:
                video_error = str(exc)
        else:
            try:
                opened = Image.open(BytesIO(image_bytes))
                original_format = opened.format
                image = opened.convert("RGB")
            except Exception:
                try:
                    import cv2
                    from ..core.video import extract_sharpest_frames
                    frames_cv = extract_sharpest_frames(image_bytes, max_frames=3)
                    is_video = True
                    image = Image.fromarray(cv2.cvtColor(frames_cv[0], cv2.COLOR_BGR2RGB))
                    original_format = "VIDEO"
                    frames = [Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) for f in frames_cv]
                except Exception as exc:
                    is_video = True
                    video_error = str(exc)
                    original_format = "VIDEO"
                    image = None

        image_info = ImageInfo(
            width=image.width if image else 0,
            height=image.height if image else 0,
            mode=image.mode if image else ("video" if is_video else "audio"),
            sha256=_hash_bytes(image_bytes),
            format=original_format,
        )
        media_type = "audio" if is_audio else "video" if is_video else "image"


        with start_span(
            "argusai.analysis",
            {
                "image.sha256": image_info.sha256,
                "image.width": image_info.width,
                "image.height": image_info.height,
                "media.type": media_type,
                "pipeline.detector_count": len(registry.all()),
            },
        ) as root_span:
            trace_id = span_trace_id(root_span)
            context: Dict[str, Any] = {
                "image_info": image_info,
                "image_bytes": image_bytes,
                "user_context": (user_context or "").strip(),
                "is_video": is_video,
                "is_audio": is_audio,
                "media_type": media_type,
                "video_error": video_error,
            }

            detectors = registry.all()

            xray_metrics = {}

            def disabled_signal(detector, reason: str) -> EvidenceSignal:
                return EvidenceSignal(
                    id=detector.id,
                    name=detector.name,
                    category=detector.category,
                    status=SignalStatus.UNAVAILABLE,
                    reliability=0.0,
                    summary="This detector was held out by the Arize reliability governor.",
                    what_checked="ArgusAI checks detector health before allowing each signal to influence the verdict.",
                    what_found=f"Recent Phoenix-tracked health data marked this detector as unhealthy: {reason}.",
                    why_it_matters="A detector that has recently failed a sanity check should not keep influencing authenticity decisions.",
                    caveat="This is a detector health decision, not evidence about the uploaded image.",
                    observations=[f"Arize reliability governor disabled detector: {reason}"],
                    metrics={
                        "governed_by_arize": True,
                        "circuit_breaker": True,
                        "circuit_breaker_reason": reason,
                    },
                    supports=SignalSupport.UNKNOWN,
                    visible=False,
                )

            def unavailable_for_media(detector, reason: str) -> EvidenceSignal:
                return EvidenceSignal(
                    id=detector.id,
                    name=detector.name,
                    category=detector.category,
                    status=SignalStatus.UNAVAILABLE,
                    reliability=0.0,
                    summary=reason,
                    what_checked="This detector is not used for this media type.",
                    what_found=reason,
                    why_it_matters="ArgusAI only shows checks that produce meaningful evidence for the uploaded media.",
                    caveat="This is not a detector failure. The signal was intentionally excluded.",
                    observations=[reason],
                    supports=SignalSupport.UNKNOWN,
                    visible=False,
                )

            async def run_detector_tracked(detector):
                if detector.id not in SIGNAL_VISIBILITY.get(media_type, set()):
                    sig = unavailable_for_media(
                        detector,
                        f"{detector.name} is calibrated for still images and is hidden for {media_type} reports.",
                    )
                    xray_metrics[detector.id] = {
                        "status": sig.status.value,
                        "support": sig.supports.value,
                        "time_seconds": 0.0,
                        "reliability": sig.reliability,
                        "confidence": sig.confidence,
                        "summary": sig.summary,
                        "visible": False,
                    }
                    return sig

                if is_video and detector.id in {"spectral_artifacts", "metadata_analysis", "error_level_analysis"} and not frames:
                    sig = unavailable_for_media(
                        detector,
                        f"{detector.name} needs extracted video frames, but frame extraction was unavailable: {video_error or 'unknown video decode error'}.",
                    ).model_copy(update={"visible": True})
                    xray_metrics[detector.id] = {
                        "status": sig.status.value,
                        "support": sig.supports.value,
                        "time_seconds": 0.0,
                        "reliability": sig.reliability,
                        "confidence": sig.confidence,
                        "summary": sig.summary,
                        "visible": True,
                    }
                    return sig

                disabled_reason = self.health_governor.disabled_reason(detector.id)
                if disabled_reason:
                    sig = disabled_signal(detector, disabled_reason)
                    xray_metrics[detector.id] = {
                        "status": sig.status.value,
                        "support": sig.supports.value,
                        "time_seconds": 0.0,
                        "reliability": sig.reliability,
                        "confidence": sig.confidence,
                        "summary": sig.summary,
                        "visible": sig.visible,
                        "governed_by_arize": True,
                        "circuit_breaker": True,
                        "circuit_breaker_reason": disabled_reason,
                    }
                    return sig

                start_time = time.perf_counter()
                with start_span(
                    f"detector.{detector.id}",
                    {"detector.id": detector.id, "detector.name": detector.name, "detector.category": detector.category},
                ) as span:
                    try:
                        if is_video and detector.id not in ("semantic_inconsistencies", "osint_verification") and frames:
                            sigs = []
                            for f in frames:
                                sigs.append(await detector.analyze(f, context))
                            ai_sigs = [s for s in sigs if s.supports == SignalSupport.AI_GENERATED]
                            if ai_sigs:
                                sig = max(ai_sigs, key=lambda s: s.confidence or 0)
                            else:
                                sig = sigs[0]
                        else:
                            sig = await detector.analyze(image, context)

                        duration = time.perf_counter() - start_time
                        health_event = self.health_governor.record_signal_health(detector.id, sig.metrics or {})
                        metric_row = {
                            "status": sig.status.value,
                            "support": sig.supports.value,
                            "time_seconds": round(duration, 4),
                            "reliability": sig.reliability,
                            "confidence": sig.confidence,
                            "summary": sig.summary,
                            "top_observation": sig.observations[0] if sig.observations else None,
                        }
                        if health_event:
                            metric_row["health_event"] = health_event
                        metric_row["visible"] = sig.visible
                        xray_metrics[detector.id] = metric_row

                        set_span_attribute(span, "detector.status", sig.status.value)
                        set_span_attribute(span, "detector.confidence", sig.confidence)
                        set_span_attribute(span, "detector.reliability", sig.reliability)
                        set_span_attribute(span, "detector.latency_seconds", round(duration, 4))
                        set_span_attribute(span, "detector.signal_support", sig.supports.value)
                        set_span_attribute(span, "detector.circuit_breaker", bool((sig.metrics or {}).get("circuit_breaker")))
                        set_span_attribute(span, "detector.circuit_breaker.reason", (sig.metrics or {}).get("circuit_breaker_reason"))
                        set_span_attribute(span, "detector.circuit_breaker.gap_score", (sig.metrics or {}).get("gap_score"))
                        return sig
                    except Exception as e:
                        duration = time.perf_counter() - start_time
                        xray_metrics[detector.id] = {"status": "CRASHED", "time_seconds": round(duration, 4), "error": str(e)}
                        try:
                            span.record_exception(e)
                        except Exception:
                            pass
                        set_span_attribute(span, "detector.status", "crashed")
                        set_span_attribute(span, "detector.latency_seconds", round(duration, 4))
                        return EvidenceSignal(
                            id=detector.id,
                            name=detector.name,
                            category=detector.category,
                            status=SignalStatus.ERROR,
                            reliability=0.0,
                            summary="FATAL DETECTOR CRASH",
                            observations=[f"Exception caught in pipeline: {str(e)}"],
                            supports=SignalSupport.UNKNOWN,
                        )

            tasks = [run_detector_tracked(detector) for detector in detectors]
            signals = await asyncio.gather(*tasks)
            if is_video:
                extra_video_signals = await self._video_extra_signals(image_bytes, signals)
                signals = [*signals, *extra_video_signals]
                for sig in extra_video_signals:
                    xray_metrics[sig.id] = {
                        "status": sig.status.value,
                        "support": sig.supports.value,
                        "time_seconds": (sig.metrics or {}).get("latency_seconds", 0.0),
                        "reliability": sig.reliability,
                        "confidence": sig.confidence,
                        "summary": sig.summary,
                        "visible": sig.visible,
                    }

            signals_by_id = {signal.id: signal for signal in signals}
            calibration_event = None
            spectral = signals_by_id.get("spectral_artifacts")
            semantic = signals_by_id.get("semantic_inconsistencies")
            if spectral and semantic:
                calibration_event = self.health_governor.record_calibration_observation(
                    spectral.supports.value,
                    semantic.supports.value,
                )
                attenuation = self.health_governor.spectral_attenuation_factor()
                if attenuation < 1.0:
                    adjusted = spectral.model_copy(
                        update={
                            "reliability": round(spectral.reliability * attenuation, 4),
                            "metrics": {
                                **(spectral.metrics or {}),
                                "calibration_divergence": True,
                                "spectral_attenuation_factor": attenuation,
                            },
                            "observations": [
                                *spectral.observations,
                                "Arize calibration governor reduced spectral influence because spectral and semantic detectors repeatedly disagreed.",
                            ],
                        }
                    )
                    signals = [adjusted if signal.id == "spectral_artifacts" else signal for signal in signals]
                    xray_metrics.setdefault("spectral_artifacts", {})["calibration_divergence"] = True
                    xray_metrics.setdefault("spectral_artifacts", {})["spectral_attenuation_factor"] = attenuation

            warnings: List[str] = []
            for signal in signals:
                if signal.visible and signal.status in {SignalStatus.ERROR, SignalStatus.UNAVAILABLE, SignalStatus.WARNING}:
                    warnings.append(f"{signal.name}: {signal.summary}")

            health_snapshot = self.health_governor.snapshot()
            evidence = EvidenceProfile(image=image_info, signals=signals, media_type=media_type, warnings=warnings, health=health_snapshot)

            reasoning_start = time.perf_counter()
            reasoning_outcome = await self.reasoning.reason(evidence)
            reasoning_duration = time.perf_counter() - reasoning_start

            total_w = reasoning_outcome.score_breakdown.total_considered
            contrib = reasoning_outcome.signal_contributions
            merged_signals = []
            for sig in evidence.signals:
                raw = contrib.get(sig.id, 0.0)
                pct = int(min(100, round(100 * raw / total_w))) if total_w > 1e-9 else 0
                set_span_attribute(root_span, f"detector.{sig.id}.verdict_influence_percent", pct)
                merged_signals.append(sig.model_copy(update={"verdict_influence_percent": pct}))
            evidence = evidence.model_copy(update={"signals": merged_signals})

            global_duration = time.perf_counter() - global_start
            pipeline_health = {
                "arize": tracing_health(),
                "detector_governor": health_snapshot,
                "model_health_label": self._model_health_label(merged_signals),
            }

            report = ForensicReport(
                media_type=media_type,
                verdict=reasoning_outcome.verdict,
                certainty=reasoning_outcome.certainty,
                confidence_label=reasoning_outcome.confidence_label,
                leaning=reasoning_outcome.leaning,
                short_summary=reasoning_outcome.short_summary,
                explanation=reasoning_outcome.explanation,
                score_breakdown=reasoning_outcome.score_breakdown,
                evidence=evidence,
                pipeline_health=pipeline_health,
                phoenix_trace_id=trace_id,
                generated_at=ForensicReport.now(),
            )

            set_span_attribute(root_span, "verdict", report.verdict.value)
            set_span_attribute(root_span, "media.type", media_type)
            set_span_attribute(root_span, "certainty", report.certainty)
            set_span_attribute(root_span, "total_detectors", len(signals))
            set_span_attribute(root_span, "failed_detectors", sum(1 for s in signals if s.status in {SignalStatus.ERROR, SignalStatus.UNAVAILABLE}))
            set_span_attribute(root_span, "pipeline.latency_seconds", round(global_duration, 4))
            set_span_attribute(root_span, "detector_health.status", health_snapshot.get("status"))
            set_span_attribute(root_span, "calibration_divergence", bool((health_snapshot.get("calibration_divergence") or {}).get("active")))
            if calibration_event:
                set_span_attribute(root_span, "calibration_divergence.event", True)

            # --- GENERATE X-RAY DIAGNOSTIC LOG ---
            xray_log = {
                "timestamp": report.generated_at.isoformat(),
                "image_hash": image_info.sha256,
                "media_type": media_type,
                "image_info": image_info.model_dump(),
                "global_execution_time": round(global_duration, 4),
                "reasoning_execution_time": round(reasoning_duration, 4),
                "detector_metrics": xray_metrics,
                "final_verdict": report.verdict.value,
                "certainty": report.certainty,
                "warnings": warnings,
                "score_breakdown": report.score_breakdown.model_dump(),
                "reasoning_summary": reasoning_outcome.summary_payload,
                "pipeline_health": pipeline_health,
                "phoenix_trace_id": trace_id,
                "llm_health": llm_settings.health_snapshot(),
            }

            log_dir = Path("logs/xray")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"xray_{image_info.sha256[:8]}_{int(time.time())}.json"

            try:
                with open(log_file, "w") as f:
                    json.dump(xray_log, f, indent=4)
            except Exception:
                pass

            persist_analysis(report, xray_metrics)

            return report

    def _model_health_label(self, signals: List[EvidenceSignal]) -> str:
        offline = [s.name for s in signals if (s.metrics or {}).get("circuit_breaker")]
        if offline:
            return f"{', '.join(offline)} offline - verdict based on remaining signals"
        return "All detector health gates operational"

    async def _video_extra_signals(self, video_bytes: bytes, base_signals: List[EvidenceSignal]) -> List[EvidenceSignal]:
        semantic = next((sig for sig in base_signals if sig.id == "semantic_inconsistencies"), None)
        temporal = self._temporal_signal_from_semantic(semantic)
        audio_track = await self._analyze_video_audio_track(video_bytes)
        return [temporal, audio_track]

    def _temporal_signal_from_semantic(self, semantic: Optional[EvidenceSignal]) -> EvidenceSignal:
        if not semantic or semantic.status in {SignalStatus.ERROR, SignalStatus.UNAVAILABLE}:
            return EvidenceSignal(
                id="temporal_coherence",
                name="Temporal Coherence",
                category="semantic",
                status=SignalStatus.UNAVAILABLE,
                reliability=0.0,
                summary="Temporal coherence could not be assessed because the video semantic review was unavailable.",
                what_checked="We look across the clip for morphing, flicker, unstable identity details, inconsistent physics, and geometry that shifts between frames.",
                what_found="The video review did not return usable temporal observations.",
                why_it_matters="AI video often looks plausible in single frames while breaking across time.",
                caveat="This is a detector availability issue, not evidence for or against the clip.",
                observations=["Temporal signal depends on the Gemini video review."],
                supports=SignalSupport.UNKNOWN,
                visible=True,
            )
        return EvidenceSignal(
            id="temporal_coherence",
            name="Temporal Coherence",
            category="semantic",
            status=semantic.status,
            reliability=0.35 if semantic.supports == SignalSupport.AUTHENTIC else 0.75,
            summary=semantic.summary,
            what_checked="We reviewed the video across time for morphing, flicker, unstable identities, impossible motion, and geometry that shifts between frames.",
            what_found=semantic.what_found or "The temporal review completed without a separate structured finding.",
            why_it_matters="AI video generators often fail across time even when individual frames look convincing.",
            caveat="Low bitrate, motion blur, and heavy compression can resemble temporal artifacts, so this signal is weighed with the rest of the evidence.",
            observations=semantic.observations,
            metrics={**(semantic.metrics or {}), "derived_from": "semantic_inconsistencies"},
            confidence=semantic.confidence,
            supports=SignalSupport.INCONCLUSIVE if semantic.supports == SignalSupport.AUTHENTIC else semantic.supports,
            notes="Derived from the Gemini video prompt focused on cross-frame consistency.",
            visible=True,
        )

    async def _analyze_video_audio_track(self, video_bytes: bytes) -> EvidenceSignal:
        start = time.perf_counter()
        try:
            from ..core.video import extract_audio_track
            audio_bytes = await asyncio.to_thread(extract_audio_track, video_bytes)
        except Exception:
            audio_bytes = None

        if not audio_bytes:
            return EvidenceSignal(
                id="audio_track",
                name="Audio Track",
                category="audio",
                status=SignalStatus.UNAVAILABLE,
                reliability=0.0,
                summary="No usable audio track was found in this video.",
                what_checked="We tried to extract a short mono WAV track from the video container and run the audio authenticity detector.",
                what_found="The clip was silent, the audio stream was unsupported, or ffmpeg was unavailable in this runtime.",
                why_it_matters="If a video includes speech, voice-clone evidence can change the investigation. Silent clips simply skip this check.",
                caveat="Unavailable audio does not affect the visual video verdict.",
                observations=["Video audio extraction returned no WAV bytes."],
                metrics={"latency_seconds": round(time.perf_counter() - start, 4)},
                supports=SignalSupport.UNKNOWN,
                visible=True,
            )

        from ..detectors.audio import analyze_audio
        sig = await analyze_audio(audio_bytes)
        return sig.model_copy(
            update={
                "id": "audio_track",
                "name": "Audio Track",
                "category": "audio",
                "summary": f"Embedded video audio: {sig.summary}",
                "metrics": {**(sig.metrics or {}), "latency_seconds": round(time.perf_counter() - start, 4)},
                "visible": True,
            }
        )

