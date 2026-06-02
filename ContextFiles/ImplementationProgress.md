# ArgusAI Implementation Progress

Last updated: June 2, 2026.

For full details, read `ContextFiles/CurrentHandoff.md`. This file is the concise progress tracker.

## Status

Backend, frontend, self-hosted Phoenix, Firestore persistence, and a local Google ADK investigator agent are implemented. Image, audio, and video analysis have been smoke-tested against the live backend. Arize/Phoenix is receiving live OpenTelemetry traces, `/stats` is Firestore-backed, the admin dashboard is wired to persistent stats plus trace data, and the ADK agent can call both ArgusAI backend tools and Phoenix MCP tools.

## Live Services

- Frontend: `https://argusai-frontend-1007754127412.us-central1.run.app`
- Backend: `https://argusai-backend-1007754127412.us-central1.run.app`
- Phoenix: `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`
- Admin password: `argusai2026`

Google Cloud:

- Project: `argusai-497719`
- Project number: `1007754127412`
- Region: `us-central1`
- Gemini secret: `argusai-gemini-api-key`
- Gemini multi-key secret: `argusai-gemini-api-keys` (35 unique keys)
- Firebase project: `argusai-8d9fe`
- Firebase service account secret: `argusai-firebase-service-account`
- Spectral weights: `gs://argusai-497719-models/models/argusai_best_weights.pth`

## Done

- FastAPI backend with image/video `/analyze`, audio `/analyze-audio`, chat, PDF, Agent Builder endpoints, Arize health, and Arize trace feed.
- React/Vite frontend with dynamic image/video/audio upload UX, media-specific copy, signal filtering, audio report rendering, Arize badge, and password-gated admin panel.
- Phoenix/OpenTelemetry tracing in backend.
- Phoenix self-hosted on Cloud Run and local Docker fallback.
- Detector health governor with calibration divergence tracking.
- Firestore persistence layer for analyses, detector stats, global stats, feedback, and health governor state; active on Cloud Run.
- `/stats` endpoint with Firestore-first, x-ray fallback behavior.
- `/sessions/{session_id}/feedback` endpoint for verdict feedback.
- Reports include `phoenix_trace_id` for admin/report audit links.
- Agent Builder `/agent/analyze` and `/agent/chat` include Firestore history context, current detector reliability stats, recent same-media cases, and Phoenix trace IDs.
- Gemini semantic prompts for image, video, and audio.
- Gemini fallback path from `gemini-3.5-flash` to `gemini-2.5-flash` for quota/high-demand/transient failures.
- Deployed Gemini key rotation across 35 keys via Secret Manager `argusai-gemini-api-keys`.
- `/arize/traces` endpoint reading Firestore first and x-ray logs as fallback for admin dashboard.
- Frontend Cloud Run deployment via `frontend/Dockerfile`.
- Frontend empirical reliability display, verdict feedback widget, admin global stats row, and Phoenix trace links.
- Verdict cards show an inline Phoenix audit link, and official PDFs include trace ID/timestamp chain-of-custody footer.
- Admin panel includes the Firestore/Phoenix explanatory framing copy for judges.
- Phoenix MCP config fixed to use `PHOENIX_DASHBOARD_URL`.
- Local ADK agent package added at `agents/argusai_investigator`.
- ADK agent uses Gemini, ArgusAI backend tools, and Phoenix MCP via `npx @arizeai/phoenix-mcp`.
- Agent action endpoints added: detector reliability, similar cases, drift detection, detector recalibration, fact-check note, and human-review artifact.

## Live Verification

Image AI sample:

- Verdict: `likely_ai_generated`
- Certainty: `0.795`
- Spectral: `ok`, supports `ai_generated`
- Semantic: `ok`, supports `ai_generated`
- Semantic model used: `gemini-2.5-flash` fallback

Audio AI sample:

- File: `Images Dataset/AI audio/Coral_and_Turquoise.mp3`
- Verdict: `ai_generated`
- Certainty: `0.95`
- Signal: Gemini semantic audio fallback
- Finding: missing breathing and overly consistent synthetic production patterns

Video AI sample:

- File: `Images Dataset/AI video/mp_.mp4`
- Verdict: `likely_ai_generated`
- Certainty: `0.906`
- Semantic: `ok`, supports `ai_generated`
- Temporal coherence: `ok`, supports `ai_generated`
- Embedded audio track: gracefully `unavailable`

Arize/Phoenix:

- Backend `/arize/health` reports tracing configured/enabled.
- Backend `/arize/traces` returns Firestore-backed traces.
- Phoenix Cloud Run logs confirm repeated `POST /v1/traces` HTTP 200.
- Local ADK Phoenix MCP verification succeeded: the agent called `phoenix_list-projects` and `phoenix_list-traces` against local Phoenix and received the `argusai-forensics` project (`UHJvamVjdDoy`) plus real traces/spans.

Firestore/Gemini:

- Backend `/stats` returns `source: firestore`.
- Backend `/health` reports `gemini_key_count: 35`.
- Live `/analyze` returned a `phoenix_trace_id` and persisted an analysis to Firestore.
- Live backend revision after ADK/agent-action endpoint work: `argusai-backend-00017-bw8`.
- Live frontend revision after Agent Builder/chain-of-custody work: `argusai-frontend-00004-4h6`.
- Backend agent action endpoints verified locally on port `8001`; `recalibrate-detector` wrote a bounded `1.0x` no-op override to Firestore for `spectral_artifacts`.
- Backend agent action endpoints verified on Cloud Run after deploy: `/agent/tools/detectors/spectral_artifacts/reliability` and `/agent/tools/accuracy-drift` returned Firestore-backed responses.
- ADK default model is `gemini-3.5-flash`; during verification Gemini 3.5 returned temporary `503 high demand`, so `ADK_GEMINI_MODEL=gemini-2.5-flash` was used once to prove tool execution.

## Remaining

1. Use the local ADK investigator agent for the demo:
   - install with `uv pip install --python .venv-adk\Scripts\python.exe -r agents\argusai_investigator\requirements.txt`
   - run with `adk run agents\argusai_investigator`
   - set `ARGUSAI_API_BASE` to the local backend port.
2. Configure Google Cloud Agent Builder tools if you still want console proof:
   - `POST https://argusai-backend-1007754127412.us-central1.run.app/agent/analyze`
   - `POST https://argusai-backend-1007754127412.us-central1.run.app/agent/chat`
   - These endpoints are no longer generic Gemini wrappers; they now query Firestore-backed history context.
3. Run the Pope puffer demo image end to end and confirm OSINT output.
4. Prepare or capture a calibration/recalibration demo moment.
5. Record the 3-minute demo.
6. Complete Devpost submission.
7. Optionally set backend/Phoenix `min-instances=1` during recording/judging to avoid cold starts and Phoenix data reset.

## Caveats

- Backend sessions are in memory. Keep backend `max-instances=1` until external session storage exists.
- Phoenix Cloud Run is unauthenticated and ephemeral. It is acceptable for hackathon/demo, not production.
- Firestore is active on Cloud Run. The code still falls back to x-ray logs if Firebase is unavailable.
- Gemini 3.5 may rate-limit; Gemini 2.5 fallback is intentional.
- Gemini Cloud Run key rotation is active with 35 keys.
- Local browser automation via Node REPL could not run because Playwright was not installed there; HTTP-level frontend checks passed.

## Validation Commands

```powershell
python -m compileall backend\app
cd frontend
npm run build
```

Useful live checks:

```powershell
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/health" | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/stats" | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/arize/health" | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/arize/traces?limit=10" | ConvertTo-Json -Depth 8
```
