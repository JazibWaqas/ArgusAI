# ArgusAI

ArgusAI is a forensic investigation platform for image, video, and audio authenticity. It is built for the Google Cloud Rapid Agent Hackathon and the Arize partner track.

ArgusAI is not a single-score classifier. It builds an evidence trail: detector findings, Gemini reasoning, public-source provenance, Phoenix traceability, and a reliability agent that can change how future verdicts are made.

> **The forensic pipeline investigates the media. A second agent investigates the forensic pipeline.**

## Live Demo

- Frontend: https://argusai-frontend-1007754127412.us-central1.run.app
- Backend API: https://argusai-backend-1007754127412.us-central1.run.app
- Backend health: https://argusai-backend-1007754127412.us-central1.run.app/health
- Demo video: <!-- TODO: paste YouTube link before submission -->`https://youtu.be/...`

The public frontend supports normal user flows: upload media, run a forensic investigation, inspect evidence cards, ask follow-up questions, and export a report.

## Hackathon Fit

The challenge asks for a functional agent powered by Gemini and Google Cloud Agent Builder, with a partner MCP integration.

ArgusAI satisfies that with:

- **Gemini** for semantic media review, grounded OSINT research, follow-up investigation, report narrative, and reliability-agent narration.
- **Google Cloud Agent Builder / ADK** through `agents/argusai_investigator`, a repo-local agent that uses Gemini, ArgusAI backend tools, and Arize Phoenix MCP.
- **Arize Phoenix MCP** through `mcp/phoenix-mcp.json` and the ADK agent's Phoenix MCP toolset.
- **Arize Phoenix observability** through OpenTelemetry traces, detector spans, LLM spans, token counts, latency, fallback telemetry, and feedback annotations.
- **A real agent action loop** where the reliability agent fuses Phoenix telemetry with Firestore outcomes and can recalibrate or bench detector influence.

## What It Does

ArgusAI investigates media using multiple evidence channels:

- Image forensics: spectral artifacts, metadata/provenance, sensor noise, lighting physics, semantic consistency, error-level analysis, and OSINT.
- Video forensics: frame extraction, temporal coherence, semantic video review, spectral checks on frames, optional embedded audio analysis, and OSINT.
- Audio forensics: voice-authenticity model, acoustic micro-signatures, Gemini semantic listening, and optional OSINT.
- Public provenance: Gemini grounded search returns research hops, earliest appearance, fact-check sources, timeline contradictions, and source context when the user provides a claim.
- Follow-up investigation: the chat agent can inspect cached media, query case history, explain detector influence, run live provenance, draft a fact-check note, and flag review.

## Reliability Agent

The operator-side reliability agent is the Arize-centered proof surface.

It reads:

- Phoenix telemetry: detector latency, errors, model calls, token counts, fallback rate, and trace health.
- Firestore outcomes: human-confirmed detector accuracy, same-media history, applied weights, and recent-vs-historical drift.

It can act:

- `recalibrate_detector_weight`: writes a bounded Firestore override consumed by future verdict scoring.
- `bench_detector`: writes `agent_benched` so a detector gets `0.0x` future verdict influence.
- `reactivate_detector`: human override that brings a benched detector back into rotation.
- `flag_for_human_review` and `draft_fact_check_note`: per-case action artifacts.

This means observability is not decorative. Phoenix telemetry helps decide which detectors earn influence.

## Architecture

```text
frontend/                 React + Vite user app and operator console
backend/app/              FastAPI backend
backend/app/core/         pipelines, reasoning, Firestore, observability, LLM client
backend/app/detectors/    forensic detectors
backend/app/reports/      PDF report generation
agents/argusai_investigator/
                           Google ADK agent with ArgusAI tools + Phoenix MCP
mcp/phoenix-mcp.json      Phoenix MCP server template
docker-compose.phoenix.yml
                           local self-hosted Phoenix for demo/replay
```

Persistent state:

- Firestore stores analyses, feedback, detector reliability, agent actions, and global stats.
- Phoenix stores the trace/audit layer for analysis runs and detector spans.

Cloud services:

- Backend Cloud Run: `argusai-backend`
- Frontend Cloud Run: `argusai-frontend`
- Phoenix Cloud Run: `argusai-phoenix`
- Firebase project: `argusai-8d9fe`

## Key API Endpoints

- `GET /health`
- `GET /stats`
- `GET /arize/health`
- `GET /arize/traces`
- `POST /sessions`
- `POST /sessions/{session_id}/analyze`
- `POST /sessions/{session_id}/messages`
- `POST /sessions/{session_id}/feedback`
- `POST /agent/analyze`
- `POST /agent/chat`
- `POST /agent/investigate`
- `GET /agent/activity`
- `GET /agent/detector-roi`
- `GET /agent/tools/accuracy-drift`
- `GET /agent/tools/similar-cases`
- `GET /agent/tools/detectors/{detector_id}/reliability`
- `POST /agent/tools/recalibrate-detector`
- `POST /agent/tools/bench-detector`
- `POST /agent/tools/reactivate-detector`
- `POST /agent/tools/draft-fact-check-note`
- `POST /agent/tools/flag-for-human-review`

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

Local Phoenix:

```powershell
docker compose -f docker-compose.phoenix.yml up -d
```

Open Phoenix at `http://localhost:6006`.

## Local ADK Agent

```powershell
uv venv .venv-adk
uv pip install --python .venv-adk\Scripts\python.exe -r agents\argusai_investigator\requirements.txt
$env:ARGUSAI_API_BASE="http://127.0.0.1:8000"
$env:ADK_GEMINI_MODEL="gemini-3.5-flash"
.\.venv-adk\Scripts\adk.exe run agents\argusai_investigator
```

The ADK agent connects to Phoenix MCP with `npx @arizeai/phoenix-mcp`.

## Phoenix MCP

Template:

```text
mcp/phoenix-mcp.json
```

For local Phoenix:

```env
PHOENIX_DASHBOARD_URL=http://localhost:6006
PHOENIX_API_KEY=
```

For the hosted Phoenix used during development:

```env
PHOENIX_DASHBOARD_URL=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app
PHOENIX_API_KEY=
```

## Environment

See `.env.example`.

Important variables:

- `GEMINI_API_KEY`
- `GEMINI_API_KEYS`
- `PHOENIX_COLLECTOR_ENDPOINT`
- `PHOENIX_DASHBOARD_URL`
- `PHOENIX_PROJECT_NAME`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_SERVICE_ACCOUNT_JSON` or `GOOGLE_APPLICATION_CREDENTIALS`
- `SPECTRAL_MODEL_PATH`
- `SPECTRAL_MODEL_GCS_URI`
- `SERPAPI_KEY`
- `VITE_API_BASE`
- `VITE_ADMIN_PASSWORD`

Do not commit real secrets or admin credentials.

## Validation

Run before deploy or submission:

```powershell
python -m compileall backend\app
cd frontend
npm run build
```

## Notes

- Backend sessions are currently in memory. Cloud Run uses `max-instances=1` so follow-up chat stays on the same instance.
- The hosted Phoenix instance is demo-grade and ephemeral.
- Large model weights and local datasets are intentionally not tracked in Git.
- The spectral model checkpoint is loaded from Google Cloud Storage in deployment.

## License

MIT License. See `LICENSE`.
