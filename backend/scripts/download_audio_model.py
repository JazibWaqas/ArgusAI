"""
Download the wav2vec2 deepfake audio detection model to a local directory.
Run once from the project root:
    .venv\\Scripts\\python -m backend.scripts.download_audio_model

The model (~500 MB) is saved to backend/models/wav2vec2-deepfake/ and will
be used automatically by the audio detector on subsequent runs, bypassing
the Hugging Face Space fallback entirely.
"""
from __future__ import annotations

import sys
from pathlib import Path

MODEL_ID = "garystafford/wav2vec2-deepfake-voice-detector"
LOCAL_DIR = Path("backend/models/wav2vec2-deepfake")
SENTINEL = LOCAL_DIR / "config.json"


def main() -> None:
    if SENTINEL.exists():
        print(f"[download_audio_model] Model already present at '{LOCAL_DIR}'. Skipping download.")
        return

    print(f"[download_audio_model] Downloading '{MODEL_ID}' → '{LOCAL_DIR}' …")
    print("  This is ~500 MB and may take a few minutes on first run.")

    try:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
    except ImportError:
        print("[download_audio_model] ERROR: 'transformers' not installed.")
        print("  Run:  pip install transformers")
        sys.exit(1)

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    print("  Downloading feature extractor …")
    fe = AutoFeatureExtractor.from_pretrained(MODEL_ID)
    fe.save_pretrained(str(LOCAL_DIR))

    print("  Downloading model weights …")
    model = AutoModelForAudioClassification.from_pretrained(MODEL_ID)
    model.save_pretrained(str(LOCAL_DIR))

    print(f"[download_audio_model] ✓ Done — model saved to '{LOCAL_DIR}'")
    print("  Restart the backend server to use the local model automatically.")


if __name__ == "__main__":
    main()
