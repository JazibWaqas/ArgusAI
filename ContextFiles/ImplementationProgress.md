# ArgusAI Implementation Progress

Last updated: May 29, 2026

## Status: BACKEND DEPLOYED — local Phoenix working — frontend and Agent Builder still pending

The backend is live on Google Cloud Run with Gemini configured through Secret Manager and spectral weights stored in Cloud Storage. Local self-hosted Arize Phoenix is also running through Docker for development and demo fallback while the hosted Arize account issue is unresolved.

---

## What Is Done (Code)

- Seven-detector FastAPI analysis pipeline, fully parallel with asyncio.gather
- Weighted evidence reasoning engine with per-detector verdict influence scoring
- Gemini-only LLM stack: vision, grounded OSINT research agent, narrative, chat
- React/Vite frontend: signal cards, Arize health badge, OSINT research panel (hops, sources, earliest appearance, timeline warning), ELA heatmap, PDF export, session chat
- Phoenix/OpenTelemetry observability: root analysis span + per-detector child spans
- Spectral circuit-breaker attributes logged to Phoenix: `circuit_breaker`, `circuit_breaker_reason`, `gap_score`
- DetectorHealthGovernor: persists circuit-breaker state across requests with configurable TTL
- `/arize/health` endpoint for frontend badge polling
- `grounded_osint_research_agent()`: multi-hop Gemini grounded search, structured JSON output with `earliest_web_appearance`, `fact_check_sources`, `timeline_contradiction`, `research_hops`
- `/agent/analyze` and `/agent/chat` endpoints for Agent Builder
- Dockerfile (CPU-only torch via --index-url, correct memory footprint)
- `requirements.txt` clean (torch installed by Dockerfile separately, not by pip -r)
- Git LFS configured via `.gitattributes` for `*.pth` and `*.pt`
- MIT LICENSE file in repo root
- `.env.example` with all required env vars documented
- `mcp/phoenix-mcp.json` for Arize Phoenix MCP server config
- `.gcloudignore` excludes local datasets, model weights, logs, virtualenvs, and frontend build output from Cloud Run source deploys
- `docker-compose.phoenix.yml` runs local self-hosted Phoenix on `http://localhost:6006`

---

## What Is Done (Cloud)

- Google Cloud project: `argusai-497719`
- Project number: `1007754127412`
- Region: `us-central1`
- Enabled APIs: Cloud Run, Cloud Build, Artifact Registry, Cloud Storage, Secret Manager, Vertex AI / AI Platform, Billing Budgets
- Artifact Registry repository: `cloud-run-source-deploy`
- Cloud Storage bucket: `gs://argusai-497719-models`
- Spectral model object: `gs://argusai-497719-models/models/argusai_best_weights.pth`
- Secret Manager secret: `argusai-gemini-api-key`
- Backend Cloud Run service: `argusai-backend`
- Backend URL: `https://argusai-backend-1007754127412.us-central1.run.app`
- Health URL: `https://argusai-backend-1007754127412.us-central1.run.app/health`
- Cloud Run settings: `4Gi` memory, `2` CPU, `300s` timeout, concurrency `1`, `min-instances=0`, `max-instances=3`
- Cloud Run Gemini model env vars currently use `gemini-3.5-flash` for text, vision, grounding, and fallback

---

## What Is Done (Local Phoenix)

- Docker container: `argusai-phoenix`
- Phoenix version observed in logs: `16.3.0`
- UI: `http://localhost:6006`
- HTTP trace collector: `http://localhost:6006/v1/traces`
- gRPC trace collector: `http://localhost:4317`
- Local `.env` is configured for:
  - `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces`
  - `PHOENIX_DASHBOARD_URL=http://localhost:6006`
  - `PHOENIX_PROJECT_NAME=argusai-forensics`
  - `ARIZE_HEALTH_GOVERNOR=1`
- Verified `backend.app.core.observability.tracing_health()` returns `configured=True`, `enabled=True`, and `error=None`.
- Verified Phoenix received trace traffic: Docker logs show multiple `POST /v1/traces HTTP/1.1" 200 OK` entries from a local ArgusAI smoke run.
- The local Phoenix setup does not require `PHOENIX_API_KEY`.

Start local Phoenix:

```powershell
docker compose -f docker-compose.phoenix.yml up -d
```

Stop local Phoenix:

```powershell
docker compose -f docker-compose.phoenix.yml down
```

---

## Remaining

1. Deploy frontend with `VITE_API_BASE=https://argusai-backend-1007754127412.us-central1.run.app`.
2. If Arize Cloud account access starts working, add Phoenix Cloud env vars to Cloud Run. Until then, use local self-hosted Phoenix for the recorded demo and trace proof.
3. Confirm Phoenix traces arrive from Cloud Run if using Phoenix Cloud. Local Phoenix tracing is already confirmed.
4. Configure Google Cloud Agent Builder tools.
5. Connect Phoenix MCP.
6. Run Pope puffer demo image end to end.
7. Record 3-minute YouTube demo.
8. Complete Devpost submission.

---

## Verified

- Python files compile: `python -m compileall backend/app` passes
- Frontend production build: `npm run build` passes
- Synthetic 64x64 PNG pipeline run returned 7 signals
- requirements.txt no longer pins torch (Dockerfile handles CPU wheel install)
- Cloud Run `/health` returns `status=ok`, Gemini ready, and all 7 detectors registered
- `/health` currently reports `spectral_model_exists=false` before first analysis because Cloud Run downloads the GCS model lazily
- Local Phoenix UI returns HTTP 200 at `http://127.0.0.1:6006/`
- Local backend tracing successfully initializes against self-hosted Phoenix
- Local Phoenix received trace POSTs from an ArgusAI smoke run
- Gemini key in Cloud Run was rotated after the original Secret Manager version returned `PERMISSION_DENIED` as leaked
- Deployed Cloud Run dataset smoke test passed with `gemini-3.5-flash`: verdict `likely_ai_generated`, certainty `0.837`, spectral detector `ok`, semantic detector `ok`, OSINT detector `warning` on a non-public-claim dataset image
