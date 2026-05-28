# ArgusAI

Forensic investigation platform for image authenticity.

ArgusAI is not a single-score deepfake detector. It runs seven parallel forensic detectors, builds an evidence trail, investigates public provenance with Gemini grounding, and uses Arize Phoenix as the audit layer for detector health.

## Hackathon Build Status

Target event: Google Cloud Rapid Agent Hackathon, Arize partner track.

Current implementation:

- FastAPI backend with session analysis, follow-up chat, PDF reports, and Agent Builder-facing endpoints.
- React/Vite frontend with upload flow, animated analysis, signal cards, OSINT research details, Arize health badge, and PDF export.
- Seven detectors running in parallel: spectral, metadata, noise, lighting, semantic vision, ELA, and OSINT.
- Gemini-only AI stack for semantic analysis, OSINT synthesis, grounded research, report narratives, and chat follow-ups.
- Arize Phoenix/OpenTelemetry instrumentation for root analysis traces and detector child spans.
- Arize reliability governor: circuit-breaker events are not passive logs. They mark a detector unhealthy and remove it from future verdict influence during the health TTL.
- OSINT research agent output: research hops, earliest appearance candidate, fact-check sources, timeline contradiction, search queries, and optional reverse-image matches when the user provides a public image URL.

Current cloud state:

- Google Cloud project: `argusai-497719`.
- Backend Cloud Run service: `argusai-backend`.
- Backend URL: `https://argusai-backend-1007754127412.us-central1.run.app`.
- Runtime region: `us-central1`.
- Cloud Run settings: `4Gi` memory, `2` CPU, `300s` timeout, concurrency `1`, `min-instances=0`, `max-instances=3`.
- Gemini key is stored in Secret Manager as `argusai-gemini-api-key`.
- Spectral weights are stored in Cloud Storage at `gs://argusai-497719-models/models/argusai_best_weights.pth`.
- The backend health endpoint is live at `https://argusai-backend-1007754127412.us-central1.run.app/health`.
- Local self-hosted Phoenix is working through Docker at `http://localhost:6006`; trace intake is confirmed through `POST /v1/traces`.

Still required:

- Run a live `/analyze` request against Cloud Run to verify spectral model download and full detector behavior.
- Deploy the frontend connected to the Cloud Run backend.
- Configure Google Cloud Agent Builder tools against `/agent/analyze` and `/agent/chat`.
- Create Phoenix Cloud space and set the Cloud Run Phoenix env vars, or use the verified self-hosted Phoenix path for the recorded demo if hosted signup remains blocked.
- Connect the official Phoenix MCP server using `mcp/phoenix-mcp.json` for prompts/datasets/experiments.
- Record the 3-minute demo.
- Confirm whether model weights can be redistributed based on training dataset licenses.

## Core Story

The winning demo framing is:

> ArgusAI investigates images like a forensic newsroom. It checks the pixels, checks the physics, checks the file, checks the live web, and checks whether its own detectors are healthy enough to vote.

The Arize integration is intentionally load-bearing. If the spectral detector fails its reference self-test, Phoenix receives the circuit-breaker trace, the reliability governor records the health event, and the verdict is based on the remaining signals. Removing Arize removes the audit trail and health governance story.

## API

- `GET /health` - runtime status, detector list, LLM readiness, Phoenix tracing state, detector governor state.
- `GET /arize/health` - compact status for the frontend Arize badge.
- `POST /sessions` - create an in-memory session.
- `POST /sessions/{session_id}/analyze` - multipart `file`, optional `context`; returns full forensic report.
- `POST /sessions/{session_id}/messages` - follow-up question about the last report.
- `POST /analyze` - direct full analysis without a session.
- `POST /agent/analyze` - Agent Builder-friendly analysis response with simplified schema.
- `POST /agent/chat` - Agent Builder-friendly follow-up endpoint.
- `GET /sessions/{session_id}/report.pdf` - PDF export for a session.
- `POST /reports/official.pdf` - PDF export from a report JSON payload.

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
- `PHOENIX_API_KEY` and `PHOENIX_COLLECTOR_ENDPOINT` - enable Phoenix tracing.
- `PHOENIX_DASHBOARD_URL` - shown in the frontend Arize badge.
- `SERPAPI_KEY` - optional reverse-image enrichment when the user includes a public image URL in context.
- `ARIZE_HEALTH_GOVERNOR=1` - keeps detector health events load-bearing.
- `SPECTRAL_MODEL_PATH=argusai_fuse_best` - spectral model directory or checkpoint path.

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
- Keep `min-instances=0` during development. Switch to `min-instances=1` only near demo/judging if cold starts hurt.

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
