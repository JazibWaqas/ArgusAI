# ArgusAI Signals

Last updated: May 29, 2026.

ArgusAI uses seven evidence signals. The goal is not to make each signal perfect. The goal is to make each signal explicit, weighted, and auditable.

## 1. Spectral Artifacts

File: `backend/app/detectors/spectral.py`

Custom Six-Lens PyTorch model:

- ConvNeXt texture branch.
- FFT frequency branch.
- SRM residual branch.
- Chroma/YCbCr branch.
- SPAI spatial predictability branch.
- Robustness perturbation branch.

Most important hackathon behavior: reference self-test. If the model collapses or fails to separate local real/AI references, it emits a circuit-breaker signal and does not influence the verdict.

## 2. Metadata and Provenance

File: `backend/app/detectors/metadata.py`

Reads EXIF metadata and looks for camera traces, software traces, and explicit generative-tool fingerprints such as Midjourney, DALL-E, Stable Diffusion, ComfyUI, or OpenAI.

## 3. Noise Pattern Analysis

File: `backend/app/detectors/noise.py`

Measures sensor-noise-like texture, high-frequency energy, variance, and smooth dead zones. Real cameras leave baseline noise. AI images often become too smooth or add artificial grain inconsistently.

## 4. Lighting Consistency

File: `backend/app/detectors/lighting.py`

Measures dynamic range, clipping, crushed shadows, and regional contrast. This detects suspiciously perfect exposure as well as authentic camera clipping.

## 5. Semantic and Physical Consistency

File: `backend/app/detectors/semantic.py`

Uses Gemini vision to inspect visible scene logic: hands, shadows, geometry, text, logos, watermarks, and impossible materials. This is the most human-readable image-only signal.

## 6. Error Level Analysis

File: `backend/app/detectors/ela.py`

Re-saves the image and measures compression residuals. Produces a base64 PNG heatmap for the UI. ELA is weak for AI-vs-real directly, but useful for edits, composites, and localized tampering.

## 7. OSINT Verification

File: `backend/app/detectors/osint.py`

Uses Gemini grounded search as a provenance research agent. Output includes:

- research hops
- earliest web appearance candidate
- named fact-check sources
- source URLs and dates
- timeline contradiction
- search queries
- optional reverse-image matches when a public image URL is supplied

This is the headline user-facing feature for the demo.

## Aggregation

File: `backend/app/reasoning/engine.py`

Each signal is weighted by:

- strategic importance
- reliability
- status factor
- directional confidence

Signals with `error` or `unavailable` status contribute zero. That is what makes the Arize reliability governor load-bearing: an unhealthy detector is not allowed to keep voting.
