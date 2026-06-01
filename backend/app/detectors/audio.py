"""
Audio deepfake detection — two-tier detector.

Tier 1 (fast, local):  wav2vec2-deepfake loaded from backend/models/wav2vec2-deepfake/
Tier 2 (fallback):     Hugging Face Space via gradio_client

Engineering decisions:
- Model is loaded ONCE at module import time (startup warm-up, not lazy).
- HF Space client is created ONCE at module level.
- All blocking I/O (HF API call, audio conversion) runs in a ThreadPoolExecutor
  so the async FastAPI event loop is never blocked.
- Audio is always converted to 16 kHz mono WAV before inference using librosa
  (handles WAV/MP3/OGG/M4A/FLAC automatically).
- Audio is clamped to 10 seconds max (model optimal range: 2.5–13 s).
- Results are SHA-256 cached in memory (TTL-less, process-scoped).
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport

log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
MODEL_LOCAL_DIR = Path(os.getenv("AUDIO_MODEL_PATH", "backend/models/wav2vec2-deepfake"))
HF_SPACE_ID = os.getenv("HF_AUDIO_SPACE_ID", "Sameer121/deepfake-audio-detector")
SAMPLE_RATE = 16_000
MAX_AUDIO_SECONDS = 10
MAX_AUDIO_SAMPLES = SAMPLE_RATE * MAX_AUDIO_SECONDS

# Thread pool for blocking inference / HF API calls (keep small — CPU-bound).
_executor = ThreadPoolExecutor(max_workers=2)

# ── SHA-256 result cache (process-scoped, no TTL) ────────────────────────────
_cache: Dict[str, EvidenceSignal] = {}

# ── Try to import heavy deps once at import time ─────────────────────────────
try:
    import librosa
    import numpy as np
    _LIBROSA_OK = True
except ImportError:
    _LIBROSA_OK = False
    log.warning("[audio] librosa not installed — local inference unavailable.")

try:
    import torch
    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
    _TORCH_OK = True
except ImportError:
    _TORCH_OK = False
    torch = None  # type: ignore
    AutoFeatureExtractor = None  # type: ignore
    AutoModelForAudioClassification = None  # type: ignore
    log.warning("[audio] torch/transformers not installed — local inference unavailable.")

try:
    from gradio_client import Client, handle_file
    _GRADIO_OK = True
except ImportError:
    _GRADIO_OK = False
    log.warning("[audio] gradio_client not installed — HF Space fallback unavailable.")


# ── Singleton local model ─────────────────────────────────────────────────────
_local_model = None
_local_fe = None
_local_device = "cpu"
_local_load_error: Optional[str] = None


def _try_load_local_model() -> None:
    """Called once at startup. Silently skips if model dir is missing."""
    global _local_model, _local_fe, _local_device, _local_load_error

    sentinel = MODEL_LOCAL_DIR / "config.json"
    if not sentinel.exists():
        log.info("[audio] Local model not found at '%s' — will use HF Space fallback.", MODEL_LOCAL_DIR)
        return

    if not _TORCH_OK or not _LIBROSA_OK:
        _local_load_error = "torch or librosa not installed"
        log.warning("[audio] Cannot load local model: %s", _local_load_error)
        return

    try:
        log.info("[audio] Loading local wav2vec2 model from '%s' …", MODEL_LOCAL_DIR)
        _local_fe = AutoFeatureExtractor.from_pretrained(str(MODEL_LOCAL_DIR))
        _local_model = AutoModelForAudioClassification.from_pretrained(str(MODEL_LOCAL_DIR))
        _local_device = "cuda" if torch.cuda.is_available() else "cpu"
        _local_model.to(_local_device)
        _local_model.eval()
        log.info("[audio] ✓ Local model ready on %s.", _local_device)
    except Exception as exc:
        _local_load_error = str(exc)
        _local_model = None
        _local_fe = None
        log.error("[audio] Failed to load local model: %s", exc)


# Warm up at import time (non-blocking from caller's perspective; runs in main thread
# during FastAPI startup before the first request arrives).
_try_load_local_model()


# ── Singleton HF Space client ─────────────────────────────────────────────────
_hf_client = None
_hf_client_error: Optional[str] = None

def _get_hf_client():
    global _hf_client, _hf_client_error
    if _hf_client is not None:
        return _hf_client
    if not _GRADIO_OK:
        _hf_client_error = "gradio_client not installed"
        return None
    try:
        log.info("[audio] Connecting to HF Space '%s' …", HF_SPACE_ID)
        _hf_client = Client(HF_SPACE_ID)
        log.info("[audio] ✓ HF Space client ready.")
    except Exception as exc:
        _hf_client_error = str(exc)
        log.error("[audio] HF Space client init failed: %s", exc)
    return _hf_client


# Eagerly init HF client in background thread at startup so first request is fast.
def _init_hf_client_bg() -> None:
    _get_hf_client()

_executor.submit(_init_hf_client_bg)


# ── Audio loading helper ──────────────────────────────────────────────────────
def _load_audio_mono_16k(audio_bytes: bytes) -> Tuple[Any, bool]:
    """
    Load raw audio bytes → numpy float32 array at 16 kHz mono.
    Clamps to MAX_AUDIO_SAMPLES.
    Returns (waveform_np, success).
    """
    if not _LIBROSA_OK:
        return None, False
    import numpy as np
    try:
        with io.BytesIO(audio_bytes) as buf:
            waveform, _ = librosa.load(buf, sr=SAMPLE_RATE, mono=True)
        # Clamp to 10 s
        if len(waveform) > MAX_AUDIO_SAMPLES:
            waveform = waveform[:MAX_AUDIO_SAMPLES]
        # Normalize amplitude
        peak = np.abs(waveform).max()
        if peak > 1e-6:
            waveform = waveform / peak
        return waveform, True
    except Exception as exc:
        log.warning("[audio] librosa load failed: %s", exc)
        return None, False


# ── Local inference (blocking — call via executor) ────────────────────────────
def _run_local_inference(audio_bytes: bytes) -> EvidenceSignal:
    t0 = time.perf_counter()
    waveform, ok = _load_audio_mono_16k(audio_bytes)
    if not ok:
        return _error_signal("local_load_failed", "librosa could not decode the audio file.")

    try:
        import numpy as np
        inputs = _local_fe(
            waveform,
            sampling_rate=SAMPLE_RATE,
            return_tensors="pt",
            padding=True,
        )
        inputs = {k: v.to(_local_device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = _local_model(**inputs).logits
            probs = torch.nn.functional.softmax(logits, dim=-1)[0]

        prob_real = float(probs[0].item())
        prob_fake = float(probs[1].item())
        latency = round(time.perf_counter() - t0, 3)

        return _build_signal(prob_real, prob_fake, "local_wav2vec2", latency)

    except Exception as exc:
        log.error("[audio] Local inference error: %s", exc)
        return _error_signal("local_inference_error", str(exc))


# ── HF Space inference (blocking — call via executor) ─────────────────────────
def _run_hf_inference(audio_bytes: bytes) -> EvidenceSignal:
    client = _get_hf_client()
    if client is None:
        return _error_signal(
            "hf_client_unavailable",
            f"HF Space client could not be initialised: {_hf_client_error or 'unknown error'}.",
        )

    t0 = time.perf_counter()
    try:
        # Write to temp file — gradio_client needs a file path or handle_file()
        suffix = ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            # Convert to wav via librosa if possible, otherwise send as-is
            if _LIBROSA_OK:
                import soundfile as sf
                waveform, ok = _load_audio_mono_16k(audio_bytes)
                if ok:
                    sf.write(tmp.name, waveform, SAMPLE_RATE, format="WAV")
                else:
                    tmp.write(audio_bytes)
            else:
                tmp.write(audio_bytes)
            tmp_path = tmp.name

        result = client.predict(handle_file(tmp_path), api_name="/predict")
        latency = round(time.perf_counter() - t0, 3)

        # Clean up
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        # Parse result — Space returns label string like "Fake (92%)" or dict
        return _parse_hf_result(result, latency)

    except Exception as exc:
        log.error("[audio] HF Space inference error: %s", exc)
        return _error_signal("hf_inference_error", str(exc))


def _parse_hf_result(result: Any, latency: float) -> EvidenceSignal:
    """
    Try to parse the Gradio Space response into prob_real / prob_fake.
    The Space may return a label string, dict, or tuple — handle all cases.
    """
    label = ""
    confidence = 0.5

    try:
        if isinstance(result, dict):
            # e.g. {"label": "Fake", "confidences": [{"label": "Real", "confidence": 0.08}, ...]}
            label = (result.get("label") or "").lower()
            for item in result.get("confidences", []):
                if str(item.get("label", "")).lower() == label:
                    confidence = float(item.get("confidence", 0.5))
        elif isinstance(result, (list, tuple)) and len(result) >= 1:
            label = str(result[0]).lower()
            if len(result) >= 2:
                confidence = float(result[1])
        else:
            label = str(result).lower()
            # Try to parse percentage from label like "Fake (92%)"
            import re
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", label)
            if m:
                confidence = float(m.group(1)) / 100.0
    except Exception:
        pass

    is_fake = "fake" in label or "ai" in label or "generated" in label or "synthetic" in label
    prob_fake = confidence if is_fake else 1.0 - confidence
    prob_real = 1.0 - prob_fake
    return _build_signal(prob_real, prob_fake, "hf_space", latency)


# ── Signal builders ───────────────────────────────────────────────────────────
def _build_signal(prob_real: float, prob_fake: float, source: str, latency: float) -> EvidenceSignal:
    is_fake = prob_fake > 0.5
    confidence = prob_fake if is_fake else prob_real

    # Map confidence to label
    if confidence >= 0.90:
        conf_label = "Very High"
    elif confidence >= 0.75:
        conf_label = "High"
    elif confidence >= 0.60:
        conf_label = "Moderate"
    else:
        conf_label = "Guarded"

    supports = SignalSupport.AI_GENERATED if is_fake else SignalSupport.AUTHENTIC
    verdict_word = "AI-generated voice" if is_fake else "authentic human voice"
    summary = (
        f"This audio appears to be {'AI-generated (TTS/voice cloning)' if is_fake else 'authentic human speech'}. "
        f"Confidence: {confidence:.0%}. Inference via {source.replace('_', ' ')}."
    )
    source_label = "🖥 Local wav2vec2 model" if source == "local_wav2vec2" else "☁ HuggingFace Space"

    return EvidenceSignal(
        id="audio_deepfake",
        name="Audio Authenticity",
        category="audio",
        status=SignalStatus.OK,
        reliability=0.82,
        summary=summary,
        what_checked=(
            "A fine-tuned Wav2Vec2-XLSR transformer (160M params) was used to classify "
            "whether this audio was recorded from a real human voice or synthesised by a "
            "text-to-speech / voice cloning system (ElevenLabs, Amazon Polly, Kokoro, etc.)."
        ),
        what_found=(
            f"The model classified this audio as a {verdict_word} with {confidence:.0%} certainty. "
            f"Probability real: {prob_real:.0%} | Probability fake: {prob_fake:.0%}."
        ),
        why_it_matters=(
            "AI voice cloning is increasingly used to fabricate statements by public figures. "
            "This check catches spectral artifacts in the audio that TTS models leave behind."
        ),
        caveat=(
            "The model was fine-tuned on 6 TTS engines. Novel cloning systems not in its training "
            "set may evade detection. Short clips (<2.5 s) or heavily compressed audio may reduce accuracy."
        ),
        observations=[
            f"Probability of AI-generated speech: {prob_fake:.0%}",
            f"Probability of real human speech: {prob_real:.0%}",
            f"Confidence level: {conf_label}",
            f"Inference source: {source_label}",
            f"Inference latency: {latency:.2f}s",
        ],
        metrics={
            "prob_real": round(prob_real, 4),
            "prob_fake": round(prob_fake, 4),
            "inference_source": source,
            "source_label": source_label,
            "confidence_label": conf_label,
            "latency_seconds": latency,
        },
        confidence=round(confidence, 4),
        supports=supports,
    )


def _error_signal(reason: str, detail: str) -> EvidenceSignal:
    return EvidenceSignal(
        id="audio_deepfake",
        name="Audio Authenticity",
        category="audio",
        status=SignalStatus.ERROR,
        reliability=0.0,
        summary=f"Audio analysis failed: {reason}.",
        observations=[detail],
        supports=SignalSupport.UNKNOWN,
        metrics={"error": reason, "detail": detail},
    )


def _unavailable_signal(reason: str) -> EvidenceSignal:
    return EvidenceSignal(
        id="audio_deepfake",
        name="Audio Authenticity",
        category="audio",
        status=SignalStatus.UNAVAILABLE,
        reliability=0.0,
        summary="Audio detector unavailable.",
        observations=[reason],
        supports=SignalSupport.UNKNOWN,
        metrics={"unavailable_reason": reason},
    )


# ── Public async interface ────────────────────────────────────────────────────
async def analyze_audio(audio_bytes: bytes) -> EvidenceSignal:
    """
    Entry point called by the audio pipeline.
    Selects local vs HF fallback automatically.
    Caches results by SHA-256.
    """
    sha = hashlib.sha256(audio_bytes).hexdigest()
    if sha in _cache:
        cached = _cache[sha]
        log.info("[audio] Cache hit for %s…", sha[:8])
        return cached

    loop = asyncio.get_event_loop()

    if _local_model is not None:
        log.info("[audio] Running LOCAL inference (sha=%s…)", sha[:8])
        sig = await loop.run_in_executor(_executor, _run_local_inference, audio_bytes)
    elif _GRADIO_OK:
        log.info("[audio] Running HF SPACE inference (sha=%s…)", sha[:8])
        sig = await loop.run_in_executor(_executor, _run_hf_inference, audio_bytes)
    else:
        sig = _unavailable_signal(
            "Neither local wav2vec2 model nor gradio_client is available. "
            "Run: python -m backend.scripts.download_audio_model  OR  pip install gradio_client"
        )

    _cache[sha] = sig
    return sig
