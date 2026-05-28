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
from ..core.health_governor import DetectorHealthGovernor
from ..core.llm import llm_settings
from ..core.observability import set_span_attribute, start_span, tracing_health
from ..models.evidence import EvidenceProfile, ImageInfo
from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from ..models.report import ForensicReport
from ..reasoning.engine import ReasoningEngine


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AnalysisPipeline:
    def __init__(self) -> None:
        self.reasoning = ReasoningEngine()
        self.health_governor = DetectorHealthGovernor()

    async def analyze(self, image_bytes: bytes, user_context: Optional[str] = None) -> ForensicReport:
        global_start = time.perf_counter()
        opened = Image.open(BytesIO(image_bytes))
        original_format = opened.format
        image = opened.convert("RGB")
        image_info = ImageInfo(
            width=image.width,
            height=image.height,
            mode=image.mode,
            sha256=_hash_bytes(image_bytes),
            format=original_format,
        )

        with start_span(
            "argusai.analysis",
            {
                "image.sha256": image_info.sha256,
                "image.width": image_info.width,
                "image.height": image_info.height,
                "pipeline.detector_count": len(registry.all()),
            },
        ) as root_span:
            context: Dict[str, Any] = {
                "image_info": image_info,
                "image_bytes": image_bytes,
                "user_context": (user_context or "").strip(),
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
                )

            async def run_detector_tracked(detector):
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

            warnings: List[str] = []
            for signal in signals:
                if signal.status in {SignalStatus.ERROR, SignalStatus.UNAVAILABLE, SignalStatus.WARNING}:
                    warnings.append(f"{signal.name}: {signal.summary}")

            health_snapshot = self.health_governor.snapshot()
            evidence = EvidenceProfile(image=image_info, signals=signals, warnings=warnings, health=health_snapshot)

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
                verdict=reasoning_outcome.verdict,
                certainty=reasoning_outcome.certainty,
                confidence_label=reasoning_outcome.confidence_label,
                leaning=reasoning_outcome.leaning,
                short_summary=reasoning_outcome.short_summary,
                explanation=reasoning_outcome.explanation,
                score_breakdown=reasoning_outcome.score_breakdown,
                evidence=evidence,
                pipeline_health=pipeline_health,
                generated_at=ForensicReport.now(),
            )

            set_span_attribute(root_span, "verdict", report.verdict.value)
            set_span_attribute(root_span, "certainty", report.certainty)
            set_span_attribute(root_span, "total_detectors", len(signals))
            set_span_attribute(root_span, "failed_detectors", sum(1 for s in signals if s.status in {SignalStatus.ERROR, SignalStatus.UNAVAILABLE}))
            set_span_attribute(root_span, "pipeline.latency_seconds", round(global_duration, 4))
            set_span_attribute(root_span, "detector_health.status", health_snapshot.get("status"))

            # --- GENERATE X-RAY DIAGNOSTIC LOG ---
            xray_log = {
                "timestamp": report.generated_at.isoformat(),
                "image_hash": image_info.sha256,
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

            return report

    def _model_health_label(self, signals: List[EvidenceSignal]) -> str:
        offline = [s.name for s in signals if (s.metrics or {}).get("circuit_breaker")]
        if offline:
            return f"{', '.join(offline)} offline - verdict based on remaining signals"
        return "All detector health gates operational"
