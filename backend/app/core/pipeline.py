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
from ..core.llm import llm_settings
from ..models.evidence import EvidenceProfile, ImageInfo
from ..models.report import ForensicReport
from ..reasoning.engine import ReasoningEngine


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class AnalysisPipeline:
    def __init__(self) -> None:
        self.reasoning = ReasoningEngine()

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

        context: Dict[str, Any] = {
            "image_info": image_info,
            "image_bytes": image_bytes,
            "user_context": (user_context or "").strip(),
        }
        detectors = registry.all()

        xray_metrics = {}

        async def run_detector_tracked(detector):
            start_time = time.perf_counter()
            try:
                sig = await detector.analyze(image, context)
                duration = time.perf_counter() - start_time
                xray_metrics[detector.id] = {
                    "status": sig.status.value,
                    "support": sig.supports.value,
                    "time_seconds": round(duration, 4),
                    "reliability": sig.reliability,
                    "confidence": sig.confidence,
                    "summary": sig.summary,
                    "top_observation": sig.observations[0] if sig.observations else None,
                }
                return sig
            except Exception as e:
                duration = time.perf_counter() - start_time
                xray_metrics[detector.id] = {"status": "CRASHED", "time_seconds": round(duration, 4), "error": str(e)}
                # Still fail gracefully
                from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
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
            if signal.status in {"error", "unavailable"}:
                warnings.append(f"{signal.name}: {signal.summary}")
            elif signal.status == "warning":
                warnings.append(f"{signal.name}: {signal.summary}")

        evidence = EvidenceProfile(image=image_info, signals=signals, warnings=warnings)
        
        reasoning_start = time.perf_counter()
        reasoning_outcome = await self.reasoning.reason(evidence)
        reasoning_duration = time.perf_counter() - reasoning_start

        total_w = reasoning_outcome.score_breakdown.total_considered
        contrib = reasoning_outcome.signal_contributions
        merged_signals = []
        for sig in evidence.signals:
            raw = contrib.get(sig.id, 0.0)
            pct = int(min(100, round(100 * raw / total_w))) if total_w > 1e-9 else 0
            merged_signals.append(sig.model_copy(update={"verdict_influence_percent": pct}))
        evidence = evidence.model_copy(update={"signals": merged_signals})

        report = ForensicReport(
            verdict=reasoning_outcome.verdict,
            certainty=reasoning_outcome.certainty,
            confidence_label=reasoning_outcome.confidence_label,
            leaning=reasoning_outcome.leaning,
            short_summary=reasoning_outcome.short_summary,
            explanation=reasoning_outcome.explanation,
            score_breakdown=reasoning_outcome.score_breakdown,
            evidence=evidence,
            generated_at=ForensicReport.now(),
        )
        
        # --- GENERATE X-RAY DIAGNOSTIC LOG ---
        global_duration = time.perf_counter() - global_start
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
            "llm_health": llm_settings.health_snapshot(),
        }
        
        # Write to logs directory
        log_dir = Path("logs/xray")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"xray_{image_info.sha256[:8]}_{int(time.time())}.json"
        
        try:
            with open(log_file, "w") as f:
                json.dump(xray_log, f, indent=4)
        except Exception:
            pass # Failsafe, don't break pipeline if OS write fails
            
        return report
