# ArgusAI Current Handoff

Last updated: June 2, 2026.

This is the current source of truth for the next LLM/session. Read this before making new implementation decisions.

## Fresh Session Instructions

If Opus/Codex/another LLM is taking over, do this first:

1. Read this file completely.
2. Read `ContextFiles/Vision.md` for the why.
3. Read `ContextFiles/Architecture.md` for how the system is wired.
4. Read `ContextFiles/AgentBuilderPhoenixSetup.md` before touching Agent Builder or MCP.
5. Run validation commands before any deploy.

Do not add new detectors, redesign the UI, or change the core product framing unless the user explicitly asks. The highest-value remaining work is demo readiness and external console configuration.

## Winning Frame

ArgusAI is a multi-modal forensic investigation platform, not a classifier.

The product should be described as:

> Forensic investigation platform, not classifier. Evidence trail, not score.

The Arize partner-track angle is load-bearing observability:

> Phoenix watches detector behavior. Detector health and calibration events affect verdict influence, and the admin panel shows that reliability layer.

The Firestore + Phoenix story:

> Firestore persists running intelligence: history, detector reliability, feedback, and stats. Phoenix records immutable audit trails for individual verdicts.

The headline differentiator (added June 2, 2026) — self-calibration:

> Users confirm verdicts. ArgusAI tracks each detector's accuracy against that human-confirmed ground truth and automatically re-weights how much each detector influences the verdict. Observability is causal to the output, and the system measurably improves itself from use. See `ContextFiles/Vision.md` → "Self-Calibration: The Closed Loop".

Do not add more detectors unless explicitly asked. The Arize Reliability Console (admin panel) was deliberately redesigned by the owner on June 2 into an intelligence surface (trust leaderboard, real-world accuracy, applied weights) — do not revert it to a flat list. UX polish and slop-removal are active, owner-requested work; the broader "do not redesign the UI" rule still holds for the main investigation flow unless asked.

## Owner Framings (clarified directly — honor these, do not re-litigate)

These were stated by the project owner across working sessions. A fresh session should treat them as settled direction:

1. **Goal is best hackathon product, not just best product.** Make high-leverage decisions. It is fine not to have covered every edge case because the demo is controlled, but everything shown must look genuinely impressive AND be genuinely meaningful — it has to stand out against other strong submissions.
2. **Arize must be genuinely useful, not decorative.** The whole point is answering "what is Arize actually doing and why is it useful." The self-calibration loop is the answer. Judges will NOT deeply audit the codebase or which layer is Firestore vs Phoenix — so do not over-engineer perfect causal attribution, but the observability/self-improvement story must be real and visibly useful, not theatre.
3. **Demo is recorded locally on the owner's laptop.** Local (localhost backend + frontend + Docker Phoenix) must be flawless; hosted Cloud Run is a bonus, not required for the recording. Local ≠ cloud (ephemeral filesystem, cold starts, Secret Manager vs `.env`) — verify locally for the demo.
4. **Product purpose:** a genuinely reliable system to expose AI-generated media (images first; audio/video added but secondary) and explain to the user what is or isn't AI, so people can keep trusting media despite AI advances. Audience: journalists, courts, social media users, fact-checkers.
5. **No AI-slop.** No useless phrasing, no filler, no emoji decoration, nothing unnecessary on screen. Everything purposeful, clean, useful. The PDF was explicitly called out as slop and cleaned up.
6. **Repo hygiene:** do not clutter the repo or create new markdown files. Update existing docs (this file, `Vision.md`). Implementation workflow: the owner has Codex for heavy implementation; Claude/Opus acts as technical product manager — clear intent and reasoning, protect the framing, review the work. (In recent sessions Claude also implemented directly when asked.)
7. **Judges do not test or access the admin panel.** They only watch the recorded demo video. At most, they will open the live website and look around as standard public users. Stop proposing edits or security/UI changes (such as exposing admin credentials or password hints in the UI) to bypass/reveal admin security for judges. Everything they need is shown in the demo.


## Live URLs

- Frontend: `https://argusai-frontend-1007754127412.us-central1.run.app`
- Backend: `https://argusai-backend-1007754127412.us-central1.run.app`
- Backend canonical URL from Cloud Run: `https://argusai-backend-ddmxiumrdq-uc.a.run.app`
- Phoenix self-hosted on Cloud Run: `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`
- Phoenix collector endpoint: `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces`
- Local Phoenix fallback: `http://localhost:6006`
- Local Phoenix collector: `http://localhost:6006/v1/traces`

Admin dashboard password:

```text
argusai2026
```

The deployed frontend bundle is verified to use the deployed backend URL, not `localhost`.

## Google Cloud Setup

- Google Cloud project: `argusai-497719`
- Project number: `1007754127412`
- Region: `us-central1`
- Active gcloud account used: `argusai838@gmail.com`
- gcloud path on this machine: `C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd`
- Artifact Registry repo: `cloud-run-source-deploy`
- Spectral weights: `gs://argusai-497719-models/models/argusai_best_weights.pth`
- Gemini API key secret: `argusai-gemini-api-key`
- Gemini multi-key secret: `argusai-gemini-api-keys` (32 sanitized unique keys, one per line; leaked keys removed June 3, 2026)
- Firebase project: `argusai-8d9fe`
- Firebase service account secret: `argusai-firebase-service-account`

Cloud Run services:

```text
argusai-backend   latest verified revision: argusai-backend-00020-742
argusai-frontend  latest verified revision: argusai-frontend-00004-4h6
argusai-phoenix   latest verified revision: argusai-phoenix-00001-dlc
```

Backend Cloud Run settings after the latest work:

```text
memory: 4Gi
cpu: 2
timeout: 300s
concurrency: 1
min-instances: 0
max-instances: 1
```

`max-instances=1` is intentional right now. Sessions are stored in memory. When max instances was higher, `/sessions` could create a session on one Cloud Run instance and the upload could hit another instance, causing `Unknown session`. Keep `max-instances=1` until session storage is moved to Redis/Firestore/DB or the frontend stops depending on stateful sessions.

Backend runtime env currently includes:

```env
SPECTRAL_MODEL_PATH=/tmp/argusai_best_weights.pth
SPECTRAL_MODEL_GCS_URI=gs://argusai-497719-models/models/argusai_best_weights.pth
SPECTRAL_AI_INDEX=1
SPECTRAL_INPUT_SIZE=224
SPECTRAL_NORMALIZE=1
OSINT_USE_GROUNDING=1
LLM_EXPLANATION_PROVIDER=gemini
LLM_EXPLANATION_MODEL=gemini-3.1-flash-lite
LLM_EXPLANATION_MAX_TOKENS=900
LLM_EXPLANATION_TIMEOUT_SECONDS=30
LLM_VISION_TIMEOUT_SECONDS=20
VIDEO_MAX_FRAMES=2
MAX_UPLOAD_MB=20
ARIZE_HEALTH_GOVERNOR=1
GEMINI_MODEL=gemini-3.5-flash
GEMINI_VISION_MODEL=gemini-3.5-flash
GEMINI_GROUNDING_MODEL=gemini-3.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-flash
PHOENIX_COLLECTOR_ENDPOINT=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces
PHOENIX_DASHBOARD_URL=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app
PHOENIX_PROJECT_NAME=argusai-forensics
GEMINI_API_KEY=Secret Manager argusai-gemini-api-key:latest
GEMINI_API_KEYS=Secret Manager argusai-gemini-api-keys:latest
FIREBASE_PROJECT_ID=argusai-8d9fe
FIREBASE_SERVICE_ACCOUNT_JSON=Secret Manager argusai-firebase-service-account:latest
```

Why fallback is `gemini-2.5-flash`: `gemini-3.5-flash` exists for the key but hit quota/high-demand errors during live testing. The code now rotates across 32 deployed Gemini keys and falls back to `gemini-2.5-flash` for HTTP 429/503/transient failures and generic request exceptions. Final report explanation prose uses `gemini-3.1-flash-lite` with a 30s timeout; semantic vision/audio/video reasoning stays on `gemini-3.5-flash`.

## Deploy Commands

Backend deploy command used:

```powershell
& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run deploy argusai-backend --source . --region us-central1 --platform managed --allow-unauthenticated --memory 4Gi --cpu 2 --timeout 300 --concurrency 1 --max-instances 1 --update-env-vars "SPECTRAL_MODEL_PATH=/tmp/argusai_best_weights.pth,SPECTRAL_MODEL_GCS_URI=gs://argusai-497719-models/models/argusai_best_weights.pth,SPECTRAL_AI_INDEX=1,SPECTRAL_INPUT_SIZE=224,SPECTRAL_NORMALIZE=1,OSINT_USE_GROUNDING=1,LLM_EXPLANATION_PROVIDER=gemini,LLM_EXPLANATION_MODEL=gemini-3.1-flash-lite,LLM_EXPLANATION_MAX_TOKENS=900,LLM_EXPLANATION_TIMEOUT_SECONDS=30,LLM_VISION_TIMEOUT_SECONDS=20,VIDEO_MAX_FRAMES=2,MAX_UPLOAD_MB=20,ARIZE_HEALTH_GOVERNOR=1,GEMINI_MODEL=gemini-3.5-flash,GEMINI_VISION_MODEL=gemini-3.5-flash,GEMINI_GROUNDING_MODEL=gemini-3.5-flash,GEMINI_FALLBACK_MODEL=gemini-2.5-flash,PHOENIX_COLLECTOR_ENDPOINT=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces,PHOENIX_DASHBOARD_URL=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app,PHOENIX_PROJECT_NAME=argusai-forensics,FIREBASE_PROJECT_ID=argusai-8d9fe" --set-secrets "GEMINI_API_KEY=argusai-gemini-api-key:latest,GEMINI_API_KEYS=argusai-gemini-api-keys:latest,FIREBASE_SERVICE_ACCOUNT_JSON=argusai-firebase-service-account:latest"
```

Phoenix deploy command used:

```powershell
& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run deploy argusai-phoenix --image arizephoenix/phoenix:latest --region us-central1 --platform managed --allow-unauthenticated --port 8080 --memory 2Gi --cpu 1 --timeout 300 --concurrency 10 --min-instances 0 --max-instances 1 --set-env-vars PHOENIX_PORT=8080,PHOENIX_HOST=0.0.0.0,PHOENIX_PROJECT_NAME=argusai-forensics
```

Frontend deploy command used:

```powershell
& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run deploy argusai-frontend --source frontend --region us-central1 --platform managed --allow-unauthenticated --memory 512Mi --cpu 1 --timeout 120 --concurrency 80 --max-instances 2
```

Frontend Cloud Run uses `frontend/Dockerfile`. The Dockerfile defaults are:

```env
VITE_API_BASE=https://argusai-backend-1007754127412.us-central1.run.app
VITE_ADMIN_PASSWORD=argusai2026
```

## What Is Done

Backend:

- `/sessions/{id}/analyze-audio` now routes to `AudioAnalysisPipeline.analyze()`.
- Fake fabricated audio signals were removed from the image/video pipeline.
- Reports include `media_type`.
- Signals include `visible`.
- Video hides still-photo-only noise and lighting cards.
- Video includes `temporal_coherence`.
- Video attempts embedded audio extraction with graceful `unavailable` if no audio/ffmpeg issue.
- Audio uses wav2vec/HF when possible and Gemini semantic fallback when the model is missing, weak, or inconclusive.
- Gemini prompts are media-aware for image, video, and audio.
- Gemini 3.5 primary now falls back to Gemini 2.5 on quota/high-demand/transient failures.
- `DetectorHealthGovernor` tracks spectral-vs-semantic calibration divergence.
- Calibration divergence can attenuate spectral influence.
- `/arize/health` returns tracing and governor state.
- `/arize/traces` reads Firestore first and falls back to local x-ray logs for recent analysis summaries in the admin panel.
- Firestore persistence layer added in `backend/app/core/firebase.py` and `backend/app/core/analysis_store.py`.
- Every image/video/audio report now persists to Firestore on Cloud Run.
- `/stats` endpoint added; reads Firestore stats and falls back to x-ray logs when Firebase is unavailable.
- `/arize/traces` now prefers Firestore analysis documents and falls back to x-ray logs.
- `/sessions/{session_id}/feedback` endpoint added for user verdict feedback.
- Health governor state now tries Firestore first and falls back to `logs/arize/detector_health.json`.
- Reports now include `phoenix_trace_id` when an OpenTelemetry span is active.
- Agent Builder endpoints exist and are history-aware: `/agent/analyze` and `/agent/chat`.
- Agent Builder endpoints now include Firestore history context: total persisted analyses, same-media counts, current detector reliability stats, recent same-media cases, and `phoenix_trace_id`.
- `/agent/chat` injects Firestore history context before Gemini answers, so the agent can discuss accumulated reliability rather than acting like a generic Gemini wrapper.
- Agent action endpoints exist under `/agent/tools/*`: detector reliability, similar cases, accuracy drift, detector recalibration, draft fact-check note, and human-review artifact.
- `/agent/tools/recalibrate-detector` writes a bounded detector weight override to Firestore; `get_learned_weights()` consumes it, so future verdicts can change.

Frontend:

- One upload flow supports image, video, and audio.
- File type is detected client-side.
- Unsupported file types are rejected before backend upload.
- Upload/processing/report copy is media-specific.
- Signal cards filter on `visible`.
- ELA heatmap only appears for images.
- Audio reports render through an audio-specific card.
- Arize badge is present.
- Admin dashboard exists behind password `argusai2026`.
- Admin dashboard pulls `/arize/health` and `/arize/traces`.
- Admin dashboard shows recent investigations, detector health, latency, and calibration events.
- Admin dashboard also pulls `/stats` and shows global analysis counts.
- Signal cards can show empirical reliability once a detector has at least 5 recorded runs.
- Verdict feedback widget posts user confirmation to `/sessions/{session_id}/feedback`.
- Trace rows and expanded signal cards can link to the Phoenix trace when `phoenix_trace_id` exists.
- Verdict cards now show an inline forensic trace chip with `View audit trail` linking to Phoenix.
- Official PDF reports include `Forensic trace ID`, Phoenix audit URL, and a chain-of-custody footer with trace ID and generation timestamp.
- Admin dashboard includes explanatory framing copy: investigation history is persisted in Firestore and each verdict's full reasoning is recorded as a Phoenix trace.

Cloud/Arize:

- Backend deployed to Cloud Run.
- Backend revision `argusai-backend-00020-742` is live with `/agent/tools/*` agent-action endpoints and latency fixes.
- Frontend deployed to Cloud Run.
- Phoenix deployed to Cloud Run using `arizephoenix/phoenix:latest`.
- Firestore is active on Cloud Run. `/stats` returns `source: firestore`.
- Cloud Run `/health` reports `gemini_key_count: 32`, `explanation_model: gemini-3.1-flash-lite`, and `explanation_timeout_seconds: 30`.
- Backend points to Phoenix collector at `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces`.
- Phoenix logs confirm repeated live `POST /v1/traces HTTP/1.1" 200 OK`.
- Admin trace feed confirms image/audio/video analysis summaries are being recorded.

Config/docs:

- `.env.example` includes deployed Phoenix and backend hints.
- `.env.example` includes Firebase env vars: `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `GOOGLE_APPLICATION_CREDENTIALS`.
- `mcp/phoenix-mcp.json` now uses `PHOENIX_DASHBOARD_URL` for `--baseUrl`, not the OTEL `/v1/traces` collector endpoint.
- `frontend/Dockerfile` and `frontend/.gcloudignore` were added for Cloud Run frontend deployment.
- Local Google ADK investigator agent exists at `agents/argusai_investigator`.
- ADK agent uses Gemini, ArgusAI backend tools, and Phoenix MCP via `npx @arizeai/phoenix-mcp`.
- ADK Phoenix MCP verification succeeded locally: `phoenix_list-projects` returned `argusai-forensics` / `UHJvamVjdDoy`, and `phoenix_list-traces` returned real traces/spans.

ADK local run commands:

```powershell
uv venv .venv-adk
uv pip install --python .venv-adk\Scripts\python.exe -r agents\argusai_investigator\requirements.txt
$env:ARGUSAI_API_BASE="http://127.0.0.1:8000"
$env:ADK_GEMINI_MODEL="gemini-3.5-flash"
.\.venv-adk\Scripts\adk.exe run agents\argusai_investigator
```

If Windows reports `[WinError 10013]` or port `8000` is stuck, run the backend on `8001` and set `ARGUSAI_API_BASE` accordingly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
$env:ARGUSAI_API_BASE="http://127.0.0.1:8001"
```

If Gemini 3.5 is temporarily high-demand during recording, use:

```powershell
$env:ADK_GEMINI_MODEL="gemini-2.5-flash"
```

## Self-Calibration + Fixes (June 2, 2026 — latest session)

This session turned the feedback loop into a real, causal self-improving system and fixed several silent failures. All changes verified by `python -m compileall` / `vite build` (both pass). Backend must be restarted to pick up the Firebase fix.

Backend:

- **Fixed silent Firebase outage:** `get_db()` in `firebase.py` was `@lru_cache`-wrapped, so one transient cold-start failure cached `None` permanently for the whole process — feedback returned 503 and nothing persisted (`/stats` silently fell back to `source: xray`). Now caches only a successful client and retries each call. Symptom to watch: `POST /feedback` → 503, real-world accuracy stuck at "awaiting confirmations".
- **Confirmed-accuracy loop:** `analysis_store.py` now tracks per-detector `confirmed_total / confirmed_correct / confirmed_accuracy` (human ground truth) separately from the circular `accuracy_rate` (self-agreement). Feedback updates these via `_record_confirmed` (handles first rating and rating flips). Global `stats/feedback` counters added for real-world accuracy.
- **Learned weights:** `get_learned_weights()` (60s TTL cache) → per-detector multiplier from confirmed accuracy; gated by `LEARNED_WEIGHT_MIN_CONFIRMATIONS` (env, default 8), bounded 0.5x–1.5x, baseline 0.6 = 1.0x.
- **Causal wiring:** `reasoning/engine.py` `_score_signal` multiplies `base_weight` by the learned multiplier. `/stats` now returns `feedback`, per-detector confirmed fields, `weight_multiplier`, and a `learned_weights` block.
- **Phoenix deep-link fix:** `observability.py` added `phoenix_ui_base()` (derives UI origin from the collector endpoint so links point where traces actually go — local or cloud) and `phoenix_project_id()` (resolves the internal base64 project ID, which Phoenix URLs require — the name `argusai-forensics` in the path 404'd). Exposed as `phoenix_link` in `/arize/health`. PDF `_trace_url` reuses these.

Frontend (`App.jsx`, `styles.css`):

- **Arize Reliability Console redesigned** from a flat list into an intelligence surface: real-world accuracy hero stat, **Detector Trust Leaderboard** (confirmed accuracy + verdict-match context + applied-weight pills ↑/↓ + trust tiers Trusted/Watch/Low/Calibrating), self-calibration banner, Detector Health + Calibration Events. Removed the misleading single-run latency bars (detectors showing 0.00s looked broken).
- Deep-links now resolve from `/arize/health` `phoenix_link` (base + project ID) instead of the hardcoded broken cloud URL + project name.
- Slop removed: emoji source labels (🖥/☁), "naked classifier output" jargon, false "results in under 30 seconds" claim (analyses take 90–180s) replaced with the auditability angle.

PDF (`reports/pdf_official.py`): media-type-aware title and language (no more hardcoded "Image"/"camera-captured" on video/audio), video reports note frame-based analysis, fixed chain-of-custody trace link, tightened limitations.

## UX, Login, New Signals, In-App Agent (June 3, 2026 — latest session)

All verified with `vite build` (passes) and backend syntax/import checks. The image detector path was left untouched on purpose; only video/audio signals were added.

Login + console as the command center:
- Soft-gate **login modal** (header "Sign in"). Admin credential (`argusai2026`) routes to a separate full-page **operator console**; everyone else uses the product as guest. Demo-grade credential check in localStorage. The old floating-lock entry and modal admin panel were removed.
- The console is now a real dashboard page (own header, Arize "why it's in the loop" band, agent status strip, trust leaderboard, drift arrows, agent activity, recent investigations, calibration events).
- **In-app investigator agent**: `POST /agent/investigate` reviews drift + reliability + Phoenix health, recalibrates drifted detectors (real, logged), and narrates via Gemini. Triggered by a "Run investigator agent" button in the console; logs a `review` action every run so the Agent Activity feed always populates. This drives the agent from the website, not the terminal. It calls the tool functions directly to avoid an HTTP self-call deadlock (the ADK agent's tools hit the backend over HTTP, so the ADK agent must run as its own process).
- `GET /agent/activity` + Firestore `agent_actions` logging behind every agent tool action (recalibrate/flag/draft/review) with before→after detail.

Two new measured, fundamental signals (additive, fully guarded — failure just hides the card):
- **Audio: Acoustic Micro-Signature** (`audio_acoustics`, librosa) — jitter, shimmer, HNR, spectral flatness. Real vocal folds vary; TTS/clones are smoother. Audio reports now show up to 4 cards (Voice Model, Acoustic Micro-Signature, Gemini Listening, OSINT-with-context), rendered through the same rich card grid as image/video.
- **Video: Sensor Noise Coherence** (`temporal_noise_coherence`) — flat-region sensor-noise floor consistency across frames. Real footage keeps a steady floor; AI video is too smooth or flickers.
- Both are tracked in Firestore and weighted in `SIGNAL_IMPORTANCE`, so the self-calibration loop will prove or down-weight them over time.

Consumer-side cleanup:
- `short_summary` is now a true one-liner (the verbose version duplicated the narrative); the narrative is reframed as "Detailed assessment".
- **Audit-trail / Phoenix links removed from the consumer side entirely** (verdict card, signal cards, audio card). Phoenix naming/links live only in the operator console now.

De-AI visual polish:
- Neutral near-black base, de-neoned brand (`#22d3ee`, was `#00e5ff`), softened background gradients, de-rainbowed hero headline, naturalized copy (removed em-dashes / filler).
- Header rebuilt as a three-zone layout: logo left, working center nav (How it works / Why ArgusAI / Sample media, anchor-scroll on the landing), Sign in (with icon) right.

Note: a later edit parallelized the audio pipeline signals with `asyncio.create_task` and added a `settings.video_max_frames` config for frame extraction.

## Firebase Status

Firestore integration is implemented and active on Cloud Run.

Configured resources:

```text
Firebase project: argusai-8d9fe
Cloud Run env: FIREBASE_PROJECT_ID=argusai-8d9fe
Secret Manager: argusai-firebase-service-account
Runtime service account access: granted roles/secretmanager.secretAccessor on the secret
```

Local dev uses `GOOGLE_APPLICATION_CREDENTIALS=C:\Users\OMNIBOOK\Documents\GitHub\ArgusAI\firebase-key.json` and `FIREBASE_PROJECT_ID=argusai-8d9fe`. `firebase-key.json` is ignored by git and must never be committed.

If Firebase is not configured, the app still works and falls back to local x-ray logs for `/stats` and `/arize/traces`.

Verified on June 3, 2026:

```text
GET /stats -> source: firestore
GET /health -> gemini_key_count: 32
POST /analyze -> returned phoenix_trace_id and persisted an analysis to Firestore
GET /arize/traces?limit=3 -> source: firestore, returned the persisted analysis
Backend deployed revision -> argusai-backend-00020-742
Frontend deployed revision -> argusai-frontend-00004-4h6
```

## Live Verification Results

These tests were run against the deployed Cloud Run backend.

Image:

```text
file: Images Dataset/AI Images/Adobe_Firefly_4_0114ba5b5c0d4b1aa36a3fbf5.jpg
media_type: image
verdict: likely_ai_generated
certainty: 0.795
semantic_status: ok
semantic_supports: ai_generated
semantic_model: gemini-2.5-flash
semantic_fallback: true
spectral_status: ok
spectral_supports: ai_generated
```

Audio:

```text
file: Images Dataset/AI audio/Coral_and_Turquoise.mp3
media_type: audio
verdict: ai_generated
certainty: 0.95
signal: audio_deepfake
source: gemini_semantic
model: gemini-2.5-flash
fallback_used: true
finding: missing natural breathing, unnaturally consistent pitch/rhythm/pronunciation
```

Video:

```text
file: Images Dataset/AI video/mp_.mp4
media_type: video
verdict: likely_ai_generated
certainty: 0.906
semantic_status: ok
semantic_supports: ai_generated
semantic_model: gemini-2.5-flash
semantic_fallback: true
temporal_status: ok
temporal_supports: ai_generated
audio_track_status: unavailable
```

Trace feed:

```text
GET https://argusai-backend-1007754127412.us-central1.run.app/arize/traces?limit=10
```

Returned Firestore-backed entries with media type, verdict, certainty, `phoenix_trace_id`, detector status, detector support, `visible`, `circuit_breaker_fired`, and `calibration_divergence`.

Phoenix collector proof:

```powershell
& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run services logs read argusai-phoenix --region us-central1 --limit 80
```

Phoenix logs showed many successful:

```text
POST 200 /v1/traces
```

## Validation Commands

Run these before any future deploy:

```powershell
python -m compileall backend\app
cd frontend
npm run build
```

Both passed after the latest changes.

Useful health checks:

```powershell
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/health" | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/stats" | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/arize/health" | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/arize/traces?limit=10" | ConvertTo-Json -Depth 8
```

Verify frontend bundle uses production backend:

```powershell
$html = Invoke-WebRequest -Uri "https://argusai-frontend-1007754127412.us-central1.run.app" -UseBasicParsing
$asset = ([regex]::Match($html.Content, 'src="(/assets/[^"]+\.js)"')).Groups[1].Value
$js = Invoke-WebRequest -Uri "https://argusai-frontend-1007754127412.us-central1.run.app$asset" -UseBasicParsing
$js.Content.Contains("https://argusai-backend-1007754127412.us-central1.run.app")
$js.Content.Contains("localhost:8000")
```

Expected:

```text
True
False
```

## Manual Work Still Required

These need user/browser interaction or product judgment.

1. Configure Google Cloud Agent Builder.
   - Tool 1: `POST https://argusai-backend-1007754127412.us-central1.run.app/agent/analyze`
   - Tool 2: `POST https://argusai-backend-1007754127412.us-central1.run.app/agent/chat`
   - See `ContextFiles/AgentBuilderPhoenixSetup.md`.

2. Connect Phoenix MCP.
   - Use `mcp/phoenix-mcp.json`.
   - Set `PHOENIX_DASHBOARD_URL=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`.
   - `PHOENIX_API_KEY` is blank for current unauthenticated self-hosted Phoenix.
   - Some UIs may not like an empty `--apiKey`; if so, remove the `--apiKey` args manually for this self-hosted setup.

3. Run the actual Pope puffer demo image end to end.
   - Need the chosen demo image ready.
   - Suggested context: `Pope Francis wearing a Balenciaga-style puffer jacket, March 2023.`
   - Confirm OSINT names useful sources/dates.

4. Prepare calibration-divergence demo shot.
   - The feature exists, but the admin panel currently shows no active divergence because latest live tests agreed: spectral and semantic both said AI.
   - For the video, either prepare a fixture/sequence that creates disagreement or use a pre-recorded trace/admin state if the demo needs this exact moment.

5. Record the 3-minute demo video.
   - Show frontend upload.
   - Show evidence trail.
   - Show admin panel with Phoenix traces.
   - Show Agent Builder configured/calling tools.
   - Show Phoenix UI if useful.

6. Devpost submission.
   - Hosted project URL: frontend Cloud Run URL.
   - Code repo URL: public GitHub repo.
   - Demo video URL.
   - Track: Arize.
   - Description should emphasize forensic investigation, Gemini, Agent Builder, and Arize/Phoenix reliability governance.

7. Consider setting `min-instances=1` near demo/judging.
   - Backend and Phoenix currently use `min-instances=0` to avoid idle spend.
   - Cold starts may be annoying during recording/judging.
   - Phoenix Cloud Run is ephemeral. If it scales to zero/restarts, in-memory Phoenix data can disappear.

## Caveats

- Current Phoenix Cloud Run deployment is unauthenticated and ephemeral. Fine for hackathon/demo, not production.
- Backend sessions are in-memory. Keep `max-instances=1` until session storage is externalized.
- Gemini 3.5 quota/high demand can happen. The fallback to Gemini 2.5 is intentional and verified.
- Audio reports have a different schema (`AudioForensicReport`) than image/video reports. Frontend handles this.
- The deployed video test had no usable embedded audio track, so `audio_track` was `unavailable`; that is graceful behavior, not a failure.
- A Node Playwright browser check was attempted through the Node REPL, but Playwright was not installed there. HTTP bundle checks passed.
- **OSINT is prompt-activated by design.** `osint_verification` shows `unavailable` when no context prompt is given — this is intended, not a bug. With a context prompt it works (e.g., the PSL/Lahore Qalanders image run found Hamariweb, March 18 2023, 32% influence).
- **RESOLVED ISSUE — latency.** A latency optimization pass was completed on June 3, 2026: final explanation generation is routed to `gemini-3.1-flash-lite` with a 30s timeout; audio sub-detectors execute concurrently via `asyncio.create_task`; video frame analysis extracts a default of 2 frames (configurable via `VIDEO_MAX_FRAMES`). This successfully resolved the reasoning-phase timeout/hanging issue.
- Self-calibration is demo-safe by design: a detector's weight stays exactly 1.0x until it has `LEARNED_WEIGHT_MIN_CONFIRMATIONS` confirmations. To demo the loop quickly without confirming 8 analyses, set `LEARNED_WEIGHT_MIN_CONFIRMATIONS=3` in `.env`.

## Best Next Tasks

1. Open the public frontend and run one image/video/audio manually.
2. Confirm admin login works with `argusai2026`.
3. Configure Agent Builder tools.
4. Connect Phoenix MCP.
5. Run and record Pope puffer OSINT.
6. Prepare one clean calibration-governor demo artifact or decide to show the detector health/admin traces without forcing divergence.
7. Write final Devpost copy.
