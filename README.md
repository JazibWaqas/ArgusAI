# ArgusAI

Forensic investigation platform for image, video, and audio authenticity.

ArgusAI is not a single-score deepfake detector. It builds an evidence trail, investigates public provenance with Gemini grounding, and uses Arize Phoenix as the audit layer for detector health.

For the latest hackathon handoff, deployment state, admin password, and next actions, read:

`ContextFiles/CurrentHandoff.md`

## Fresh Session Reading Order

If another LLM or engineer is taking over, read these in order:

1. `ContextFiles/CurrentHandoff.md` - live deployment state, passwords, revisions, verification, exact remaining tasks.
2. `ContextFiles/Vision.md` - product strategy, why Firestore plus Phoenix matters, Agent Builder story.
3. `ContextFiles/Architecture.md` - backend/frontend/Firestore/Phoenix architecture.
4. `ContextFiles/ImplementationProgress.md` - concise progress tracker.
5. `ContextFiles/AgentBuilderPhoenixSetup.md` - exact Agent Builder and Phoenix MCP setup instructions.

Do not start by adding detectors or redesigning the UI. The system is already built; the remaining work is configuration, demo verification, OSINT demo quality, and final submission narrative.

## Hackathon Build Status

Target event: Google Cloud Rapid Agent Hackathon, Arize partner track.

Current implementation:

- FastAPI backend with session analysis, follow-up chat, PDF reports, and Agent Builder-facing endpoints.
- React/Vite frontend with image/video/audio upload flow, animated analysis, signal cards, OSINT research details, Arize health badge, admin dashboard, and PDF export.
- Media-specific forensic signals: spectral, metadata, noise/lighting for images, semantic reasoning, ELA, OSINT, temporal coherence for video, and audio authenticity for recordings.
- Gemini-only AI stack for semantic analysis, OSINT synthesis, grounded research, report narratives, and chat follow-ups.
- Arize Phoenix/OpenTelemetry instrumentation for root analysis traces and detector child spans.
- Arize reliability governor: circuit-breaker and calibration events are not passive logs. They affect detector influence and are visible in the admin panel.
- Firestore persistence layer for accumulated analysis history, detector reliability stats, global stats, verdict feedback, and health governor state.
- Agent Builder endpoints that use Firestore history context before responding, so the agent can discuss accumulated detector reliability and recent same-media cases.
- Phoenix chain-of-custody links surfaced in verdict cards, signal details, admin trace rows, Agent Builder responses, and official PDFs.
- Repo-local Google ADK investigator agent in `agents/argusai_investigator`, with ArgusAI backend tools and Phoenix MCP tools.
- Cloud Run Gemini rotation across 32 sanitized keys through Secret Manager.
- OSINT research agent output: research hops, earliest appearance candidate, fact-check sources, timeline contradiction, search queries, and optional reverse-image matches when the user provides a public image URL.

Current cloud state:

- Google Cloud project: `argusai-497719`.
- Backend Cloud Run service: `argusai-backend`.
- Backend URL: `https://argusai-backend-1007754127412.us-central1.run.app`.
- Frontend Cloud Run service: `argusai-frontend`.
- Frontend URL: `https://argusai-frontend-1007754127412.us-central1.run.app`.
- Phoenix Cloud Run service: `argusai-phoenix`.
- Phoenix URL: `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`.
- Runtime region: `us-central1`.
- Backend Cloud Run settings: `4Gi` memory, `2` CPU, `300s` timeout, concurrency `1`, `min-instances=0`, `max-instances=1`.
- Gemini single-key fallback is stored in Secret Manager as `argusai-gemini-api-key`.
- Gemini multi-key rotation is stored in Secret Manager as `argusai-gemini-api-keys` and currently contains 32 sanitized unique keys.
- Firebase project: `argusai-8d9fe`; service account secret: `argusai-firebase-service-account`.
- Spectral weights are stored in Cloud Storage at `gs://argusai-497719-models/models/argusai_best_weights.pth`.
- The backend health endpoint is live at `https://argusai-backend-1007754127412.us-central1.run.app/health`.
- Backend `/stats` is live and returns Firestore-backed stats.
- Backend `/agent/analyze` and `/agent/chat` are live and history-aware; they still need to be configured in the Agent Builder console.
- Phoenix trace intake is confirmed through Cloud Run logs showing `POST /v1/traces` HTTP 200.
- Admin dashboard password: `argusai2026`.

Still required:

- Configure Google Cloud Agent Builder tools against `/agent/analyze` and `/agent/chat`.
- Connect the official Phoenix MCP server using `mcp/phoenix-mcp.json` for prompts/datasets/experiments.
- Run the Pope puffer image end to end and confirm OSINT sources/dates.
- Prepare or capture a calibration-governor demo moment.
- Record the 3-minute demo.
- Confirm whether model weights can be redistributed based on training dataset licenses.

## Core Story

The winning demo framing is:

> ArgusAI investigates images like a forensic newsroom. It checks the pixels, checks the physics, checks the file, checks the live web, and checks whether its own detectors are healthy enough to vote.

The Arize integration is intentionally load-bearing. If the spectral detector fails its reference self-test, Phoenix receives the circuit-breaker trace, the reliability governor records the health event, and the verdict is based on the remaining signals. Removing Arize removes the audit trail and health governance story.

Firestore and Phoenix are both intentional:

- Firestore is persistent intelligence: analysis history, detector reliability, feedback, stats, and health state.
- Phoenix is the immutable audit trail: what happened in this verdict, which detectors ran, and how the system reached the decision.

Demo line:

> Firestore tells us how reliable each signal has been. Phoenix proves exactly what happened in this verdict.

## API

- `GET /health` - runtime status, detector list, LLM readiness, Phoenix tracing state, detector governor state.
- `GET /arize/health` - compact status for the frontend Arize badge and admin panel.
- `GET /stats` - Firestore-backed global and per-detector reliability stats, with x-ray fallback.
- `GET /arize/traces` - recent analysis traces from Firestore, with x-ray fallback for the admin dashboard.
- `POST /sessions` - create an in-memory session.
- `POST /sessions/{session_id}/analyze` - multipart `file`, optional `context`; returns full forensic report.
- `POST /sessions/{session_id}/messages` - follow-up question about the last report.
- `POST /sessions/{session_id}/feedback` - verdict feedback loop, stored in Firestore when configured.
- `POST /analyze` - direct full analysis without a session.
- `POST /agent/analyze` - Agent Builder-friendly analysis response with simplified schema.
- `POST /agent/chat` - Agent Builder-friendly follow-up endpoint.
- `GET /agent/tools/detectors/{detector_id}/reliability` - agent tool for detector reliability and applied weight.
- `GET /agent/tools/accuracy-drift` - agent tool for recent-vs-historical confirmed accuracy drift.
- `GET /agent/tools/similar-cases` - agent tool for prior same-media investigations.
- `POST /agent/tools/recalibrate-detector` - agent action that writes a bounded detector weight override.
- `POST /agent/tools/draft-fact-check-note` - agent action artifact for a citable note.
- `POST /agent/tools/flag-for-human-review` - agent action artifact for human review.
- `GET /sessions/{session_id}/report.pdf` - PDF export for a session.
- `POST /reports/official.pdf` - PDF export from a report JSON payload.

## Local ADK Agent

```powershell
uv venv .venv-adk
uv pip install --python .venv-adk\Scripts\python.exe -r agents\argusai_investigator\requirements.txt
$env:ARGUSAI_API_BASE="http://127.0.0.1:8000"
$env:ADK_GEMINI_MODEL="gemini-3.5-flash"
.\.venv-adk\Scripts\adk.exe run agents\argusai_investigator
```

The ADK agent connects to Phoenix MCP with `npx @arizeai/phoenix-mcp`. If Gemini 3.5 is temporarily high-demand, set `ADK_GEMINI_MODEL=gemini-2.5-flash` for the demo run.

## Local Setup

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\uvicorn backend.app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE=http://localhost:8000` if needed.

Local Phoenix:

```powershell
docker compose -f docker-compose.phoenix.yml up -d
```

Open `http://localhost:6006`.

## Environment

See `.env.example`.

Important variables:

- `GEMINI_API_KEY` - required for semantic vision, OSINT grounding, narrative explanation, and chat.
- `GEMINI_API_KEYS` - optional multiline/comma-separated key list for deployed multi-key rotation.
- `PHOENIX_API_KEY` and `PHOENIX_COLLECTOR_ENDPOINT` - enable Phoenix tracing.
- `PHOENIX_DASHBOARD_URL` - shown in the frontend Arize badge.
- `SERPAPI_KEY` - optional reverse-image enrichment when the user includes a public image URL in context.
- `ARIZE_HEALTH_GOVERNOR=1` - keeps detector health events load-bearing.
- `SPECTRAL_MODEL_PATH=argusai_fuse_best` - spectral model directory or checkpoint path.
- `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `GOOGLE_APPLICATION_CREDENTIALS` - Firestore persistence.

For local self-hosted Phoenix, use:

```env
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
PHOENIX_PROJECT_NAME=argusai-forensics
PHOENIX_DASHBOARD_URL=http://localhost:6006
ARIZE_HEALTH_GOVERNOR=1
```

`PHOENIX_API_KEY` can stay empty for local Phoenix.

## Detector Notes

The spectral detector has the most important reliability behavior. On load, it can run a small reference self-test against local real/AI folders. If the class gap collapses, it returns a circuit-breaker signal:

- `circuit_breaker=True`
- `circuit_breaker_reason=reference_self_test_failed`
- `gap_score=<measured gap>`

The pipeline traces that event to Phoenix and records it in `logs/arize/detector_health.json`. While active, future analyses treat the detector as unavailable so it cannot influence the verdict.

## Deployment Notes

Cloud Run currently uses CPU PyTorch, 4GiB memory, 2 CPU, and `min-instances=0` to avoid idle spend during setup.

Important deployment details:

- The Dockerfile installs CPU-only PyTorch before `backend/requirements.txt`.
- `.gcloudignore` excludes local datasets, logs, virtualenvs, frontend build output, and model weights from the build context.
- `SPECTRAL_MODEL_GCS_URI` points Cloud Run to the private GCS checkpoint.
- `SPECTRAL_MODEL_PATH=/tmp/argusai_best_weights.pth` in Cloud Run.
- `SPECTRAL_REFERENCE_REAL_DIR=""` and `SPECTRAL_REFERENCE_AI_DIR=""` in Cloud Run so the container skips local reference-set self-test.
- Keep backend `max-instances=1` while sessions are in memory.
- Keep `min-instances=0` during development. Switch backend/Phoenix to `min-instances=1` only near demo/judging if cold starts or Phoenix data reset hurt the demo.

## Demo Plan

Use one image: the viral Pope Francis white puffer jacket image.

Flow:

1. Upload image with context: `Is this a real photo of Pope Francis in a white puffer jacket?`
2. Show seven detectors running.
3. Open OSINT card: research hops, named fact-checkers, dates, provenance.
4. Show verdict and detector influence.
5. Show Arize badge and Phoenix trace.
6. Show a prepared circuit-breaker trace where spectral self-test failed and ArgusAI removed that detector from the verdict.

Do not spend demo time on PDF export, raw JSON, or multiple images.
