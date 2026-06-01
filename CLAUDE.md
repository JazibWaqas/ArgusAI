# CLAUDE.md — ArgusAI Hackathon Source of Truth

Last updated: June 2, 2026.

This file is the master alignment document. Every implementation decision, open question, bug, UX decision, and todo lives here. Codex reads this and uses it as a senior technical supervisor handoff — not micromanagement, but full clarity so implementation can proceed without ambiguity.

## Current Handoff — Read First

The freshest implementation/deployment state is captured in:

`ContextFiles/CurrentHandoff.md`

If anything below conflicts with `ContextFiles/CurrentHandoff.md`, trust `ContextFiles/CurrentHandoff.md`. Older sections in this file still explain product strategy and rationale, but many historical "todo", "bug", and "pending" items were completed by June 2, 2026. Do not treat old backlog sections as current work unless they are repeated in `ContextFiles/CurrentHandoff.md` or `ContextFiles/ImplementationProgress.md`.

Fresh takeover order:

1. `ContextFiles/CurrentHandoff.md`
2. `ContextFiles/Vision.md`
3. `ContextFiles/Architecture.md`
4. `ContextFiles/ImplementationProgress.md`
5. `ContextFiles/AgentBuilderPhoenixSetup.md`

Do not add detectors or redesign the UI unless explicitly requested. The project is in final hackathon/demo mode.

Current live state:

- Frontend: `https://argusai-frontend-1007754127412.us-central1.run.app`
- Backend: `https://argusai-backend-1007754127412.us-central1.run.app`
- Phoenix: `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`
- Admin dashboard password: `argusai2026`
- Backend is pinned to `max-instances=1` because sessions are currently in memory.
- Phoenix receives live OpenTelemetry traces from Cloud Run; logs confirmed `POST /v1/traces` with HTTP 200.
- Image, audio, and video were all tested against the live backend and returned AI-generated verdicts on the provided AI samples.
- Gemini 3.5 is the preferred model, but Gemini 2.5 Flash is the verified fallback for quota/high-demand/transient failures.
- Agent Builder endpoints now include Firestore history context, detector reliability stats, recent same-media cases, and Phoenix trace IDs.
- Verdict cards and official PDFs now surface Phoenix chain-of-custody audit links/trace IDs.
- Admin panel now explains the Firestore persistence + Phoenix immutable trace story directly for judges.

Remaining highest-leverage work:

1. Configure Google Cloud Agent Builder tools for `/agent/analyze` and `/agent/chat` in the Agent Builder console.
2. Connect Phoenix MCP using `mcp/phoenix-mcp.json`.
3. Run the Pope puffer image end to end and verify OSINT sources/dates.
4. Prepare or record the calibration-governor demo moment.
5. Record the 3-minute demo and finish Devpost copy.

---

## What ArgusAI Is

ArgusAI is a **multi-modal forensic investigation platform**. It analyzes images, video, and audio to determine whether they are likely authentic or AI-generated/synthetic.

It is not a classifier. It does not output a single number. It produces an **evidence trail** — what each independent check found, what that means in plain English, and why you should or should not trust the verdict.

The system now handles three media types:
- **Image**: The original use case. Seven signals, full pipeline.
- **Video**: Frame extraction, temporal analysis, optionally audio track extraction.
- **Audio**: Wav2Vec2 voice authenticity + Gemini semantic + OSINT.

Core product phrase to preserve everywhere in code, copy, and prompts:
> Forensic investigation platform, not classifier. Evidence trail, not score.

Target users for demo narrative: journalists, fact-checkers, content moderation teams, anyone verifying a viral image/video/audio clip before trusting or publishing it.

---

## Hackathon Requirements (Hard Constraints)
Properly detailed in **`./ContextFiles/HackathonRules.md`**
- **Agent**: Gemini + Google Cloud Agent Builder. Endpoints `/agent/analyze` and `/agent/chat` exist. Agent Builder tools must be configured against them before submission.
- **Arize**: Meaningful Phoenix integration. "Meaningful" = causally affects the product, not just logging.
- **Hosted URL**: Frontend deployed and accessible. Backend already live on Cloud Run.
- **Public GitHub**: MIT license already in place.
- **3-minute demo video**: Recorded on local machine. We control everything on screen.

Judging is equal weight across: technological implementation, design/UX, potential impact, quality/creativity of idea.

---

## Strategic Direction

The Arize story is the competition differentiator. Most competing submissions will log traces and call it Arize integration. ArgusAI's story is:

> Phoenix is the audit layer that makes the verdict trustworthy. When a detector's behavior becomes unreliable — detected via calibration divergence between peer detectors — Phoenix logs it, the health governor attenuates that detector's verdict influence, and the user sees the impact in real time.

This is observability that is **causal to the output**, not decorative.

The demo can be recorded against the deployed Cloud Run stack. Self-hosted Phoenix is available in two forms: local Docker at `http://localhost:6006` and public Cloud Run Phoenix at `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`. Cloud Run tracing to the public Phoenix collector is confirmed working.

---

## Architecture Overview

### Backend

```
FastAPI (main.py)
├── /sessions/{id}/analyze          → AnalysisPipeline (images + video)
├── /sessions/{id}/analyze-audio    → AudioAnalysisPipeline (standalone audio)
├── /sessions/{id}/chat             → LLMClient.followup_answer
├── /sessions/{id}/export-pdf       → PDF generation
├── /arize/health                   → tracing_health() + governor state
├── /arize/traces                   → NEW: query local Phoenix for recent traces
├── /agent/analyze                  → Agent Builder endpoint
└── /agent/chat                     → Agent Builder endpoint

AnalysisPipeline (pipeline.py)
├── Detects media type from magic bytes
├── Routes video through frame extraction (video.py)
├── Routes audio (embedded in video) through audio track extraction
├── Runs detector subset based on media type
├── Wraps in Phoenix spans
└── Records detector health via DetectorHealthGovernor

AudioAnalysisPipeline (audio_pipeline.py)
└── Standalone audio: wav2vec2 + OSINT + Gemini semantic

DetectorHealthGovernor (health_governor.py)
├── Persists health state to logs/arize/detector_health.json
├── NEW: Calibration divergence detection (spectral vs semantic disagreement)
└── NEW: Emits calibration_divergence span attribute when triggered

LLMClient (llm_client.py)
├── Semantic vision (image/video/audio aware)
├── Grounded OSINT research agent
├── Explanation generation (media-type aware)
└── Follow-up chat
```

### Frontend

```
App.jsx (single page, dynamic)
├── Upload zone (image/video/audio auto-detected)
├── Media type badge shown immediately on file selection
├── Processing state with appropriate copy per media type
├── Report view (adapts to media type)
│   ├── Verdict card
│   ├── Signal cards (filtered per media type)
│   ├── OSINT research panel
│   ├── ELA heatmap (image only)
│   ├── Chat
│   └── PDF export
├── Arize health badge (top-right, always visible)
└── Admin modal (login-gated, vendor-only)
    ├── Recent traces from /arize/traces
    ├── Detector latency breakdown
    ├── Circuit breaker / calibration events
    └── Health governor state
```

---

## Signal Mapping Per Media Type

This is the source of truth for which signals run and which display. The backend runs what makes sense; the frontend only renders signals marked visible for that media type.

### Image
| Signal | Runs | Displayed | Notes |
|---|---|---|---|
| spectral_artifacts | ✅ | ✅ | Core signal |
| metadata_analysis | ✅ | ✅ | EXIF + generator fingerprints |
| noise_pattern_analysis | ✅ | ✅ | Sensor noise |
| lighting_consistency | ✅ | ✅ | Physics check |
| semantic_inconsistencies | ✅ | ✅ | Gemini vision |
| error_level_analysis | ✅ | ✅ | ELA heatmap |
| osint_verification | ✅ | ✅ | Grounded search |

### Video
| Signal | Runs | Displayed | Notes |
|---|---|---|---|
| spectral_artifacts | ✅ | ✅ | Runs on extracted frames |
| metadata_analysis | ✅ | ✅ | Video container metadata |
| noise_pattern_analysis | ❌ | ❌ | Meaningless on video frames — hide |
| lighting_consistency | ❌ | ❌ | Designed for stills — hide |
| semantic_inconsistencies | ✅ | ✅ | Gemini sees frames |
| error_level_analysis | ✅ | ✅ | On extracted frames |
| osint_verification | ✅ | ✅ | Investigate the depicted event |
| temporal_coherence | ✅ NEW | ✅ NEW | Gemini analyzes inter-frame consistency |
| audio_track | ✅ NEW | ✅ NEW | Extract audio from video, run wav2vec2 |

### Audio (standalone)
| Signal | Runs | Displayed | Notes |
|---|---|---|---|
| audio_deepfake | ✅ | ✅ | wav2vec2 — the real detector |
| semantic_inconsistencies | ✅ | ✅ | Gemini listens for AI cadence/artifacts |
| osint_verification | ✅ | ✅ | Investigate claimed speaker/context |
| Everything else | ❌ | ❌ | Not applicable, do not show |

The report response from the backend should include a `media_type` field (`"image"`, `"video"`, `"audio"`) and each signal should include a `visible` boolean so the frontend filters without needing its own media type logic.

---

## Bugs That Must Be Fixed (Non-Negotiable)

### BUG-1: Audio endpoint routes to wrong pipeline
**File**: `backend/app/main.py`
**Problem**: `analyze-audio` endpoint calls `pipeline.analyze()` (the image/video pipeline) instead of `audio_pipeline.analyze()`. This means audio goes through all 7 image detectors and returns a `ForensicReport` instead of an `AudioForensicReport`.
**Fix**: Route `/sessions/{id}/analyze-audio` to `AudioAnalysisPipeline.analyze()`. Return the audio report schema. The frontend must handle both report shapes.

### BUG-2: Fake audio signals in the image pipeline
**File**: `backend/app/core/pipeline.py`
**Problem**: Functions `_analyze_audio_noise`, `_analyze_audio_reverb`, `_analyze_audio_ela` return hardcoded fabricated data ("noise floor is uniform at -45 dB", "RT60 decay rate is stable at 0.35s"). These numbers are not measured. They are made up.
**Fix**: Remove these functions entirely. Audio routing through the image pipeline should not happen. Once BUG-1 is fixed, these become dead code and should be deleted.

### BUG-3: Media-type language throughout
**Files**: `backend/app/reasoning/engine.py`, `backend/app/core/llm_client.py`
**Problem**: `_build_short_summary`, `_build_fallback_explanation`, and the LLM explanation prompt all say "real photograph", "camera-captured", "looks like a real photograph" regardless of media type.
**Fix**: Pass `media_type` from the evidence profile into the reasoning engine. Branch all copy:
- Image: "photograph", "camera-captured", "real photo"
- Video: "footage", "video", "real recording"
- Audio: "recording", "speech", "authentic human voice"

### BUG-4: Video signals producing misleading results
**Problem**: Noise pattern and lighting consistency detectors run on video frames and produce results that were calibrated for JPEG photographs. They are not wrong in a catastrophic way, but they are unreliable enough that they can flip a video verdict from AI-generated to inconclusive. Your partner observed this: "other signals were saying non-AI" on clearly synthetic video.
**Fix**: Per the signal mapping table above — do not run these detectors on video. The pipeline should skip them based on `media_type`. The reasoning engine should not score signals marked as `visible=False`.

### BUG-5: Frontend calls everything a "photo"
**File**: `frontend/src/App.jsx`
**Problem**: All formatting helpers, verdict copy, and support labels use photo/image language regardless of what was uploaded.
**Fix**: The report now includes `media_type`. Pass this to all formatting functions. Update `formatSupportLabel`, `formatVerdict`, and any other copy functions to branch on `media_type`.

---

## New Features to Build

### FEATURE-1: Media type detection and badge on upload
**Where**: Frontend, `App.jsx`
**Behavior**: When a user selects a file, immediately detect the media type from the MIME type or file extension. Show a small badge on the upload card: "📷 Image", "🎬 Video", "🎵 Audio". This sets the user's expectation before the analysis starts. If the file type is unsupported, show an error inline (do not let it reach the backend).
**Supported MIME types for each**:
- Image: `image/jpeg`, `image/png`, `image/webp`, `image/gif`, `image/bmp`
- Video: `video/mp4`, `video/webm`, `video/quicktime`, `video/x-mkvideo`
- Audio: `audio/wav`, `audio/mp3`, `audio/mpeg`, `audio/ogg`, `audio/flac`, `audio/m4a`, `audio/mp4`

### FEATURE-2: Signal filtering in the frontend report
**Where**: Frontend, `App.jsx`
**Behavior**: The report response includes `media_type` and each signal has a `visible` boolean. The frontend renders only visible signals. The signal card grid adapts: image shows ~6 cards, video shows ~5 cards, audio shows 3 cards.
**Edge case**: If a signal is marked `visible=False`, it must not appear anywhere in the UI — not even as a collapsed or greyed-out card. Absence is cleaner than a disabled state.

### FEATURE-3: Temporal coherence signal for video
**Where**: Backend, new detector or within the semantic detector
**What it does**: When media type is video, Gemini receives a prompt specifically asking about inter-frame consistency: do objects maintain consistent physics across frames? Do faces morph or shift? Do backgrounds flicker or glitch? Is there any evidence of frame-level AI generation artifacts that only appear across time rather than within a single frame?
**Signal ID**: `temporal_coherence`
**Reliability**: 0.75
**Implementation note**: This can be implemented inside `semantic_inconsistencies` with a branch on `media_type`, or as a separate detector. Either is acceptable. The key is the Gemini prompt changes when processing video.

### FEATURE-4: Audio track extraction from video
**Where**: Backend, `pipeline.py` or `video.py`
**What it does**: When a video file is uploaded, after extracting visual frames, also extract the audio track. Run it through `analyze_audio()`. Include the result as an additional signal (`audio_track`) in the video report.
**Technical approach**: Use `librosa` or `soundfile` with a raw byte approach. If the video has no audio track, skip gracefully — do not error. The signal should be marked `status=UNAVAILABLE` with explanation "No audio track found in video."
**Edge case**: Videos with no audio track (screencasts, silent renders) must not crash the pipeline.

### FEATURE-5: Calibration divergence detection in health governor
**Where**: `backend/app/core/health_governor.py` + `backend/app/core/pipeline.py`
**What it does**: After each analysis, compare the `supports` value of `spectral_artifacts` and `semantic_inconsistencies`. If they disagree (one says AUTHENTIC, other says AI_GENERATED) for 3 consecutive requests, the health governor marks a `calibration_divergence` event. This event:
1. Attenuates the spectral detector's verdict influence weight to 0.5x for the next 10 requests (or configurable TTL).
2. Emits a `calibration_divergence=True` span attribute in the Phoenix trace.
3. Is stored in `logs/arize/detector_health.json`.
4. Causes the Arize health badge to turn amber with message "Calibration alert — spectral detector weight reduced."
**This is the key Arize demo moment**: the system autonomously governing itself based on Phoenix-observed behavior.

### FEATURE-6: Admin panel (vendor view)
**Where**: Frontend, modal or drawer in `App.jsx`
**Access**: A small, subtle "Admin" link or lock icon in the bottom-left corner of the screen (not prominent — users won't notice it). Clicking opens a modal asking for a password. Password is hardcoded in the frontend env (`VITE_ADMIN_PASSWORD`) — this is a demo, not a security product.
**Contents of the admin panel**:
1. **Recent Traces**: Calls `/arize/traces` endpoint. Shows the last 10 analysis runs as a table: timestamp, media type, verdict, certainty, total latency.
2. **Detector Health**: Shows current state from `/arize/health`. Which detectors are healthy, which are in warning/error/circuit-breaker state.
3. **Calibration Events**: If any `calibration_divergence` events are in the health file, show them as alert cards with explanation.
4. **Detector Latency Chart**: For the most recent trace, show a bar chart of each detector's latency. Makes Phoenix data visually compelling.
**This panel is only shown in the demo to the operator. Judges never navigate to it themselves.**

### FEATURE-7: `/arize/traces` backend endpoint
**Where**: `backend/app/main.py`
**What it does**: Reads the x-ray log files from `logs/xray/` and returns a structured summary of recent analyses. Does NOT require querying Phoenix directly — the x-ray logs already capture verdict, certainty, signal results, and latency. This is simpler and more reliable than querying Phoenix's internal API.
**Response shape**:
```json
{
  "traces": [
    {
      "timestamp": "2026-06-01T15:30:00Z",
      "sha256": "abc123",
      "media_type": "image",
      "verdict": "likely_ai_generated",
      "certainty": 0.84,
      "latency_seconds": 8.3,
      "detectors": {
        "spectral_artifacts": {"status": "ok", "latency": 2.1, "support": "ai_generated"},
        "semantic_inconsistencies": {"status": "ok", "latency": 3.2, "support": "ai_generated"}
      },
      "circuit_breaker_fired": false,
      "calibration_divergence": false
    }
  ]
}
```

---

## UX Decisions

### Upload Experience
- Upload zone accepts all three media types via one zone. No separate tabs for image/video/audio — this is confusing and unnecessary.
- File type is auto-detected. The zone copy changes based on what's hovered/selected: "Drop image, video, or audio to investigate."
- Max file size indicator should be visible: "Images up to 10MB · Videos up to 20MB · Audio up to 10MB"
- After file selection, show a preview: image thumbnail, video duration + first frame thumbnail, audio waveform or just filename + duration.
- Context field remains optional with placeholder: "Describe the claimed context... (e.g. 'Pope Francis wearing a puffer jacket, 2023')"

### Processing State
- The processing spinner/animation should have media-type-specific copy:
  - Image: "Analyzing pixels, metadata, and web sources..."
  - Video: "Extracting frames, analyzing motion, checking audio track..."
  - Audio: "Analyzing voice patterns and checking public records..."
- Show a subtle progress indicator if possible. Even a fake timed progress bar is better than a static spinner for perceived performance.

### Report Layout
- Verdict card is always first, always prominent.
- Signal cards are always second, in a responsive grid.
- OSINT panel is always third (if applicable).
- ELA heatmap is only shown for image. Do not show for video or audio.
- Chat is always available after any analysis type.
- "Export PDF" button — keep for image. For video/audio, it still works but is less critical.

### Signal Card Wording Per Media Type
Each signal card has `what_checked`, `what_found`, `why_it_matters`, and `caveat`. These fields must adapt to media type:
- `spectral_artifacts` on video: "what_checked" should say "extracted frames from this video" not "this image"
- `semantic_inconsistencies` on video: "what_checked" should say "visual content across frames" not "the photograph"
- `semantic_inconsistencies` on audio: "what_checked" should say "the audio recording" and describe cadence, breathing, artifacts
- `audio_deepfake` on audio: already has correct wording
- `osint_verification` on audio: "what_checked" should say "the claimed speaker and context"

### Support Label Formatting
The `formatSupportLabel(support, mediaType)` function:
- Image: "Suggests authentic photograph" / "Suggests AI-generated image"
- Video: "Suggests real footage" / "Suggests AI-generated video"
- Audio: "Suggests authentic human voice" / "Suggests AI-generated / cloned speech"

### Admin Panel UX
- A small lock icon (🔒) in the footer or bottom-left corner. Not labeled "Admin" — just an icon.
- Clicking opens a simple modal with a password field. One hardcoded password.
- Wrong password: shake animation, clear field.
- Correct password: modal changes to the admin dashboard.
- Admin dashboard sections:
  - "Recent Investigations" table (from `/arize/traces`)
  - "Detector Health" status grid (from `/arize/health`)
  - "Calibration Alerts" (if any divergence events present)
- Admin panel has a "Close" button. Session persists until refresh (localStorage flag).
- Design should match the existing dark theme but feel more technical/internal — monospace fonts for trace IDs, subtle amber for warnings, red for errors.

### Arize Badge
- Currently exists in the header. Keep it.
- Normal state: green dot, "Arize · All systems nominal"
- Calibration divergence active: amber dot, "Arize · Calibration alert — spectral detector weight reduced"
- Detector circuit-breaker active: orange dot, "Arize · Detector anomaly — reliability adjusted"
- Phoenix unavailable: grey dot, "Arize · Tracing offline"
- Clicking the badge navigates to the admin panel (if logged in) or shows a tooltip "Monitoring active via Phoenix" if not.

---

## Prompt and LLM Changes Required

### `llm_client.py` — `analyze_image_semantics`
Currently has separate branches for audio vs image. The video branch is missing.
- When `media_type == "video"`, change the prompt to emphasize:
  - Temporal artifacts visible across frames
  - Morphing, flickering, inconsistent physics
  - Text or background geometry that shifts between frames
  - Do NOT say "this image" or "this photograph" — say "this video footage" or "across these frames"

### `llm_client.py` — `grounded_osint_research_agent`
Currently partially media-type aware (has audio branch). Add video branch:
- For video: "You are investigating a video clip. Use Google Search to determine the provenance of what is depicted. Is this footage from a real documented event? Has it been flagged as manipulated or AI-generated?"
- For audio: already handled (has audio-specific prompt)
- For image: unchanged

### `llm_client.py` — `_gemini_text_explanation`
The system prompt (`_get_reasoner_system_prompt`) is entirely image-specific. It must:
- Accept `media_type` as a parameter
- For video: "You are writing the explanation section of a video verification report..." and replace "photograph" with "footage" or "video" throughout
- For audio: "You are writing the explanation section of an audio authenticity report..." and replace visual references with audio equivalents

### `reasoning/engine.py` — `_build_short_summary` and `_build_fallback_explanation`
Pass `media_type` through from the evidence profile. Replace all hardcoded "real photograph" and "camera-captured" strings with a helper that returns the correct noun for the media type.

### `reasoning/engine.py` — `SIGNAL_IMPORTANCE` weights
When running with fewer signals (audio: 3 signals, video: 5-7 signals), the existing importance weights are calibrated for 7 signals. The certainty calculation may underestimate confidence because `total_considered` is lower. Consider normalizing by number of signals that actually ran, or accept that audio/video reports will naturally show lower certainty scores (which is honest — fewer signals means less certainty).

---

## What "Done" Looks Like For Each Area

### Backend — Done When:
- [ ] `analyze-audio` endpoint correctly calls `AudioAnalysisPipeline.analyze()` and returns `AudioForensicReport`
- [ ] Fake audio signals (`_analyze_audio_noise`, `_analyze_audio_reverb`, `_analyze_audio_ela`) removed from `pipeline.py`
- [ ] `AnalysisPipeline` accepts `media_type` and skips noise/lighting signals for video
- [ ] Each signal in the pipeline response includes `visible: bool` based on media type
- [ ] Report response always includes `media_type` field
- [ ] Temporal coherence Gemini signal implemented for video
- [ ] Audio track extraction from video implemented (graceful skip if no audio track)
- [ ] `health_governor.py` tracks spectral vs semantic agreement across rolling window
- [ ] Calibration divergence triggers weight attenuation + Phoenix span attribute
- [ ] `/arize/traces` endpoint implemented, reads from x-ray logs, returns structured JSON
- [ ] All LLM prompts in `llm_client.py` are media-type aware (no "photograph" for video/audio)
- [ ] Reasoning engine `_build_short_summary` and `_build_fallback_explanation` are media-type aware

### Frontend — Done When:
- [ ] File selection shows media type badge immediately
- [ ] Upload zone handles image/video/audio MIME types correctly
- [ ] Unsupported file types rejected with inline error message before backend call
- [ ] Processing state shows media-type-specific copy
- [ ] Signal cards are filtered by `visible` field from the report
- [ ] Signal card copy (what_checked etc.) is correct for each media type
- [ ] Support labels (`formatSupportLabel`) are media-type aware
- [ ] Verdict copy is media-type aware (no "photograph" for video/audio)
- [ ] ELA heatmap only rendered for image
- [ ] Admin panel accessible via lock icon in footer
- [ ] Admin panel shows recent traces table from `/arize/traces`
- [ ] Admin panel shows detector health grid from `/arize/health`
- [ ] Admin panel shows calibration alert card when divergence is active
- [ ] Arize badge reflects calibration divergence state (amber when active)
- [ ] Clicking Arize badge when logged in as admin opens admin panel

### Demo — Done When:
- [ ] Pope puffer image analysis runs cleanly: OSINT names Snopes or equivalent, verdict is AI-generated, Phoenix trace visible in admin panel
- [ ] Known AI voice clip runs cleanly: wav2vec2 gives high confidence, audio report language is correct
- [ ] Known AI deepfake video runs cleanly: temporal coherence signal appears, audio track signal appears if video has audio
- [ ] Calibration divergence can be triggered: run 3 analyses where spectral and semantic disagree, admin panel shows the alert, badge turns amber
- [ ] Admin panel visually looks polished enough for a 30-second screen-recording segment
- [ ] Local Phoenix is running (`docker compose -f docker-compose.phoenix.yml up -d`) and traces are visible at `localhost:6006`

---

## Known Open Questions (Must Answer Before or During Implementation)

**Q1: Does librosa/soundfile extract audio from MP4 video files natively?**
Answer needed before implementing audio track extraction. If not, may need `ffmpeg` as a subprocess or `av` (PyAV) library. PyAV is the cleanest Python option for this. Add to requirements.txt if needed. Cloud Run Dockerfile must include the dependency.

**Q2: What is the HF Space ID for the audio fallback?**
Currently `HF_AUDIO_SPACE_ID=Sameer121/deepfake-audio-detector` in `audio.py`. Is this Space still live and working? Test it. If it returns 404 or errors, the fallback path fails silently.

**Q3: Does the spectral model exist at the local path for demo runs?**
`SPECTRAL_MODEL_PATH=argusai_fuse_best` — does this file exist on the demo laptop? If not, every image analysis will fall back to a no-spectral-model path. Verify before the demo.

**Q4: What deepfake video will be used for the demo?**
Need to identify and test a specific video that produces a clear AI-generated verdict. The Pope puffer image is confirmed. The audio clip and deepfake video need equivalents.

**Q5: What is the admin panel password?**
Set `VITE_ADMIN_PASSWORD` in frontend `.env`. Choose something simple for the demo (e.g., `argusai2026`).

---

## Demo Script (3 Minutes)

**[0:00–0:30] — The Investigation Starts**
"Most deepfake detectors give you a number. ArgusAI gives you evidence."
Upload Pope puffer image with context: "Pope Francis wearing a Balenciaga-style puffer jacket, March 2023."
Show 7 detectors running in parallel. Watch them complete.

**[0:30–1:15] — The Evidence Trail**
Walk through the result:
- Spectral: AI frequency signature detected.
- Semantic: Gemini found irregular fabric texture and lighting inconsistencies.
- OSINT: Name-drop the actual fact-checker that appeared (Snopes, Reuters, etc.), earliest appearance date.
- Verdict card: LIKELY AI GENERATED, certainty shown.
Emphasize: "This isn't a score. It's an explanation."

**[1:15–1:45] — Multi-Modal: Audio**
"Now, the same investigation, but for audio."
Upload known AI voice clip (have it ready). Show 3-signal audio report. Language says "recording" and "voice." OSINT checks if the speaker ever said this publicly.

**[1:45–2:15] — The Arize Layer**
Click the admin toggle. Show the admin panel.
"Behind every analysis, Arize Phoenix is watching."
Show the trace table — the Pope image analysis shows up with detector latencies.
Show the detector health grid.
If calibration divergence has been prepared: "When our spectral and visual detectors start disagreeing consistently, Phoenix catches it. The system automatically reduces the spectral detector's influence on the verdict — and tells you why."
Show the amber badge.

**[2:15–2:45] — Agent Builder Compliance Shot**
Quick screenshot or 20-second clip showing Agent Builder configured with the `/agent/analyze` and `/agent/chat` tools. One test call. Done.

**[2:45–3:00] — Close**
"ArgusAI: forensic investigation, not classification. Built with Gemini, governed by Arize."
GitHub link. Live URL.

---

## Engineering Rules

1. Do not add more detectors beyond the 7 image detectors + temporal_coherence + audio_deepfake. The system is already wide enough.
2. Do not redesign the UI from scratch. Extend what exists.
3. Do not add text detection. The domain is crowded and the demo story doesn't support it.
4. Every LLM prompt must be media-type aware. "Photograph" must never appear in an audio or video report.
5. Every bug fix must be verified by running an actual analysis, not just by reading the code.
6. The calibration divergence feature is the highest-leverage new backend feature. Prioritize it after the bugs.
7. The admin panel is the highest-leverage new frontend feature. It makes Arize visible in the demo.
8. Keep the demo focused: one image, one audio clip, one video. Do not improvise during recording.

---

## Cloud Infrastructure (Unchanged)

- Google Cloud project: `argusai-497719`
- Project number: `1007754127412`
- Region: `us-central1`
- Backend service: `argusai-backend`
- Backend URL: `https://argusai-backend-1007754127412.us-central1.run.app`
- Cloud Run: 4Gi memory, 2 CPU, 300s timeout, concurrency 1, min-instances=0
- Gemini key: Secret Manager `argusai-gemini-api-key`
- Spectral weights: `gs://argusai-497719-models/models/argusai_best_weights.pth`
- Frontend: deploy to Firebase Hosting or Vercel with `VITE_API_BASE=https://argusai-backend-1007754127412.us-central1.run.app`

## Local Phoenix (For Demo)

- Docker container: `argusai-phoenix`
- Start: `docker compose -f docker-compose.phoenix.yml up -d`
- Stop: `docker compose -f docker-compose.phoenix.yml down`
- UI: `http://localhost:6006`
- Trace collector: `http://localhost:6006/v1/traces`
- Local `.env`: `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces`, `PHOENIX_DASHBOARD_URL=http://localhost:6006`, `PHOENIX_PROJECT_NAME=argusai-forensics`
- `PHOENIX_API_KEY` not needed for local Phoenix

## Environment Variables

See `.env.example` for full list. Key variables:
- `GEMINI_API_KEY` — required for all LLM calls
- `PHOENIX_COLLECTOR_ENDPOINT` — set to `http://localhost:6006/v1/traces` for demo
- `PHOENIX_PROJECT_NAME=argusai-forensics`
- `ARIZE_HEALTH_GOVERNOR=1` — enables the health governor
- `SPECTRAL_MODEL_PATH` — path to `.pth` file for spectral model
- `SERPAPI_KEY` — optional, enables Google Lens reverse-image search
- `VITE_API_BASE` — frontend env pointing to backend URL
- `VITE_ADMIN_PASSWORD` — frontend env for admin panel password

---

## Arize Hackathon Repo Reference

The official Arize starter repo (`https://github.com/Arize-ai/gemini-hackathon`) shows how to wire Phoenix MCP into an ADK agent so the agent can query Phoenix at runtime. The pattern used: `phoenix.otel.register()` for tracing (which we already do), plus the `@arizeai/phoenix-mcp` server for MCP-based read access to trace data.

For ArgusAI: the `/arize/traces` endpoint reading from x-ray logs is simpler and more reliable than querying Phoenix via MCP from the frontend. The Phoenix MCP is still relevant for Agent Builder — the agent could query Phoenix to understand past analysis quality.

---

## Progress Tracking

Work through this in order. Each item is blocked only by the items above it in the same section.

### Phase 1: Fix What's Broken (No New Features)
1. Fix BUG-1: Audio routing
2. Fix BUG-2: Remove fake audio signals
3. Fix BUG-3: Media-type language in reasoning engine
4. Fix BUG-4: Skip noise/lighting signals for video in pipeline
5. Fix BUG-5: Frontend media-type copy
6. Add `media_type` to report response
7. Add `visible` boolean to each signal based on media_type
8. Verify by running: image analysis, audio analysis, video analysis — all return correct shapes, no "photograph" in audio/video reports

### Phase 2: New Backend Features
9. Temporal coherence Gemini signal for video
10. Audio track extraction from video (with graceful fallback)
11. Calibration divergence detection in health governor
12. `/arize/traces` endpoint

### Phase 3: New Frontend Features
13. Media type badge on file selection
14. Signal filtering based on `visible` field
15. Support label and verdict copy media-type fix
16. Admin panel (lock icon → modal → password → dashboard)
17. Arize badge reflects calibration divergence state

### Phase 4: Demo Preparation
18. Verify spectral model exists on demo laptop
19. Find and test demo video (AI-generated, clear verdict)
20. Find and test demo audio clip (AI-generated voice, clear verdict)
21. Run full Pope puffer end-to-end, confirm OSINT names real sources
22. Trigger and capture calibration divergence in admin panel
23. Record the 3-minute demo
24. Deploy frontend with live backend URL
25. Configure Agent Builder tools against `/agent/analyze` and `/agent/chat`
26. Final Devpost submission
