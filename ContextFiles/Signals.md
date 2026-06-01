# ArgusAI Signals

Last updated: June 2, 2026.

ArgusAI uses media-specific evidence signals. The goal is not to make every signal perfect. The goal is to make every signal explicit, weighted, auditable, and honest about applicability.

Signals are not the final verdict. They are evidence for the reasoning layer.

## Universal Signal Rules

- Every signal has a stable `id`.
- Every signal has `status`, `supports`, `confidence`, `reliability`, and explanatory fields.
- Every signal can be hidden with `visible=false` when it is not meaningful for the current media type.
- Signals with `error` or `unavailable` status contribute zero to the verdict.
- The health governor can attenuate or remove unreliable detector influence.
- Firestore accumulates detector stats so the UI and Agent Builder can show empirical reliability once enough runs exist.
- Phoenix records detector spans so each signal is auditable.

## Image Signals

### 1. Spectral Artifacts

File: `backend/app/detectors/spectral.py`

Custom PyTorch model using ConvNeXt/SRM/chroma/frequency-style features. This is one of the strongest image signals.

Important reliability behavior:

- local/dev reference self-test can detect class-index or model-collapse issues
- failed self-test emits a circuit-breaker signal
- health governor prevents an unhealthy spectral detector from dominating the verdict
- Phoenix records circuit-breaker attributes

### 2. Metadata and Provenance

File: `backend/app/detectors/metadata.py`

Reads EXIF/container metadata and looks for camera traces, software traces, and explicit generative-tool fingerprints such as Midjourney, DALL-E, Stable Diffusion, ComfyUI, OpenAI, and related generator markers.

Missing metadata alone is not treated as proof of AI generation.

### 3. Noise Pattern Analysis

File: `backend/app/detectors/noise.py`

Measures sensor-noise-like texture, high-frequency energy, variance, and overly smooth dead zones. Real camera images often have sensor noise; generated images can be too smooth or inconsistently textured.

Image-only. Do not show/score this for standalone audio or video reports.

### 4. Lighting Consistency

File: `backend/app/detectors/lighting.py`

Measures dynamic range, clipping, crushed shadows, and regional contrast. Useful for suspiciously perfect exposure or physically odd lighting.

Image-only. Do not show/score this for standalone audio or video reports.

### 5. Semantic and Physical Consistency

File: `backend/app/detectors/semantic.py`

Uses Gemini to inspect scene logic. For images/video this includes visible anomalies such as hands, shadows, geometry, text, logos, watermarks, materials, and impossible structures.

For audio, Gemini semantic listening can help when the audio model is missing, weak, or inconclusive.

### 6. Error Level Analysis

File: `backend/app/detectors/ela.py`

Re-saves image/frame content and measures compression residuals. Produces a base64 PNG heatmap for the UI.

ELA is weak as a standalone AI detector, but useful for edits, composites, and localized tampering.

### 7. OSINT Verification

File: `backend/app/detectors/osint.py`

Uses Gemini grounded search as a provenance research agent.

Output includes:

- research hops
- earliest web appearance candidate
- named fact-check sources
- source URLs and dates
- timeline contradiction
- search queries
- optional reverse-image matches when a public image URL is supplied

This is the most user-facing demo signal. It should make the product feel like an investigation, not a model score.

## Video Signals

Video is routed through the image/video pipeline but must stay video-aware.

Displayed/scored:

- spectral artifacts on extracted frames
- metadata/container review
- semantic video review
- ELA on extracted frames
- OSINT verification
- temporal coherence
- embedded audio track when available

Hidden/not scored:

- still-photo noise pattern analysis
- still-photo lighting consistency

### Temporal Coherence

Checks whether motion, object continuity, lighting shifts, and frame-to-frame consistency look physically plausible.

This is important because many generated videos look convincing in individual frames but unstable over time.

### Embedded Audio Track

Attempts to extract audio from video with ffmpeg. If ffmpeg is missing, extraction fails, or the clip is silent, the signal returns `unavailable` gracefully.

Unavailable embedded audio is not a pipeline failure.

## Audio Signals

Standalone audio uses `AudioAnalysisPipeline`.

Displayed/scored:

- `audio_deepfake`
- semantic audio listening/context when applicable
- OSINT verification when there is a claim/speaker/event context

Hidden/not scored:

- image spectral/metadata/noise/lighting/ELA cards unless explicitly adapted for audio

### Audio Deepfake / Voice Authenticity

Uses local wav2vec2 model when available and a fallback path when the local model is missing. Gemini semantic audio can identify obvious synthetic speech patterns such as unnatural cadence, missing breathing, overly consistent pitch, or production artifacts.

## Aggregation

File: `backend/app/reasoning/engine.py`

Each signal is weighted by:

- strategic importance
- reliability
- status factor
- directional confidence
- media applicability
- health governor attenuation

The reasoning layer should ignore hidden signals and unavailable/error signals.

## Empirical Reliability

Firestore stores detector stats over time:

- `total_runs`
- `correct_count`
- `accuracy_rate`
- `avg_latency_seconds`

The frontend shows:

```text
Based on N analyses · X% accuracy
```

only after a detector has at least 5 runs.

Agent Builder endpoints also receive this reliability context through `build_history_context()`.
