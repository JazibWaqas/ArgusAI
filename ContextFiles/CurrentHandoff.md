# ArgusAI Current Handoff

Last updated: June 1, 2026.

This is the current source of truth for the next LLM/session. Read this before making new implementation decisions.

## Winning Frame

ArgusAI is a multi-modal forensic investigation platform, not a classifier.

The product should be described as:

> Forensic investigation platform, not classifier. Evidence trail, not score.

The Arize partner-track angle is load-bearing observability:

> Phoenix watches detector behavior. Detector health and calibration events affect verdict influence, and the admin panel shows that reliability layer.

Do not add more detectors or redesign the UI unless explicitly asked. The remaining work is demo readiness, Agent Builder/MCP setup, and final polish.

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

Cloud Run services:

```text
argusai-backend   latest verified revision: argusai-backend-00011-wfl
argusai-frontend  latest verified revision: argusai-frontend-00002-hd9
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
LLM_EXPLANATION_MAX_TOKENS=900
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
```

Why fallback is `gemini-2.5-flash`: `gemini-3.5-flash` exists for the key but hit quota/high-demand errors during live testing. The code now falls back to `gemini-2.5-flash` for HTTP 429/503/transient failures and generic request exceptions.

## Deploy Commands

Backend deploy command used:

```powershell
& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run deploy argusai-backend --source . --region us-central1 --platform managed --allow-unauthenticated --memory 4Gi --cpu 2 --timeout 300 --concurrency 1 --max-instances 3 --update-env-vars "SPECTRAL_MODEL_PATH=/tmp/argusai_best_weights.pth,SPECTRAL_MODEL_GCS_URI=gs://argusai-497719-models/models/argusai_best_weights.pth,SPECTRAL_AI_INDEX=1,SPECTRAL_INPUT_SIZE=224,SPECTRAL_NORMALIZE=1,OSINT_USE_GROUNDING=1,LLM_EXPLANATION_PROVIDER=gemini,LLM_EXPLANATION_MAX_TOKENS=900,MAX_UPLOAD_MB=20,ARIZE_HEALTH_GOVERNOR=1,GEMINI_MODEL=gemini-3.5-flash,GEMINI_VISION_MODEL=gemini-3.5-flash,GEMINI_GROUNDING_MODEL=gemini-3.5-flash,GEMINI_FALLBACK_MODEL=gemini-2.5-flash,PHOENIX_COLLECTOR_ENDPOINT=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces,PHOENIX_DASHBOARD_URL=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app,PHOENIX_PROJECT_NAME=argusai-forensics" --set-secrets "GEMINI_API_KEY=argusai-gemini-api-key:latest"
```

After deploy, pin backend to one instance:

```powershell
& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run services update argusai-backend --region us-central1 --max-instances 1
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
- `/arize/traces` reads local x-ray logs and returns recent analysis summaries for the admin panel.
- Agent Builder endpoints exist: `/agent/analyze` and `/agent/chat`.

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

Cloud/Arize:

- Backend deployed to Cloud Run.
- Frontend deployed to Cloud Run.
- Phoenix deployed to Cloud Run using `arizephoenix/phoenix:latest`.
- Backend points to Phoenix collector at `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces`.
- Phoenix logs confirm repeated live `POST /v1/traces HTTP/1.1" 200 OK`.
- Admin trace feed confirms image/audio/video analysis summaries are being recorded.

Config/docs:

- `.env.example` includes deployed Phoenix and backend hints.
- `mcp/phoenix-mcp.json` now uses `PHOENIX_DASHBOARD_URL` for `--baseUrl`, not the OTEL `/v1/traces` collector endpoint.
- `frontend/Dockerfile` and `frontend/.gcloudignore` were added for Cloud Run frontend deployment.

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

Returned recent entries for video and audio with media type, verdict, certainty, latency, detector status, detector support, `visible`, `circuit_breaker_fired`, and `calibration_divergence`.

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

## Best Next Tasks

1. Open the public frontend and run one image/video/audio manually.
2. Confirm admin login works with `argusai2026`.
3. Configure Agent Builder tools.
4. Connect Phoenix MCP.
5. Run and record Pope puffer OSINT.
6. Prepare one clean calibration-governor demo artifact or decide to show the detector health/admin traces without forcing divergence.
7. Write final Devpost copy.

