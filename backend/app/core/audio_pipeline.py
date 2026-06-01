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

from ..detectors.audio import analyze_audio
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
            verdict=verdict,
            certainty=round(certainty, 4),
            confidence_label=confidence_label,
            explanation=explanation,
            signal=signal,
            inference_source=inference_source,
            pipeline_health={"latency_seconds": duration, "sha256": sha},
        )

        # Write xray log
        try:
            log_dir = Path("logs/xray")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"audio_xray_{sha[:8]}_{int(time.time())}.json"
            with open(log_file, "w") as f:
                json.dump(
                    {
                        "sha256": sha,
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
