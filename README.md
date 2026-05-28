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

Still required outside code:

- Deploy to Google Cloud Run.
- Configure Google Cloud Agent Builder tools against `/agent/analyze` and `/agent/chat`.
- Create Phoenix Cloud space and set the Phoenix env vars.
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

## Environment

See `.env.example`.

Important variables:

- `GEMINI_API_KEY` - required for semantic vision, OSINT grounding, narrative explanation, and chat.
- `PHOENIX_API_KEY` and `PHOENIX_COLLECTOR_ENDPOINT` - enable Phoenix tracing.
- `PHOENIX_DASHBOARD_URL` - shown in the frontend Arize badge.
- `SERPAPI_KEY` - optional reverse-image enrichment when the user includes a public image URL in context.
- `ARIZE_HEALTH_GOVERNOR=1` - keeps detector health events load-bearing.
- `SPECTRAL_MODEL_PATH=argusai_fuse_best` - spectral model directory or checkpoint path.

## Detector Notes

The spectral detector has the most important reliability behavior. On load, it can run a small reference self-test against local real/AI folders. If the class gap collapses, it returns a circuit-breaker signal:

- `circuit_breaker=True`
- `circuit_breaker_reason=reference_self_test_failed`
- `gap_score=<measured gap>`

The pipeline traces that event to Phoenix and records it in `logs/arize/detector_health.json`. While active, future analyses treat the detector as unavailable so it cannot influence the verdict.

## Deployment Notes

Cloud Run should use CPU PyTorch and at least 2GiB memory. For demo reliability, 4GiB and one warm instance are safer.

The Dockerfile exists, but before final deployment:

- Build and run the container locally.
- Confirm the spectral model path works inside the image.
- Decide whether weights are shipped by Git LFS or downloaded from Cloud Storage at startup.
- Set `SPECTRAL_REFERENCE_REAL_DIR=""` and `SPECTRAL_REFERENCE_AI_DIR=""` in Cloud Run if reference images are not packaged.

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
