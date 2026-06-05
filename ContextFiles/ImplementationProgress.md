# ArgusAI Implementation Progress

Last updated: June 5, 2026.

For full details, read `ContextFiles/CurrentHandoff.md`. This file is the concise progress tracker. See the June 5 section in `CurrentHandoff.md` for the operator-console strategy, the Phoenix instrumentation, and the cross-store reliability analyst.

## June 5, 2026 snapshot

- Phoenix is now genuinely instrumented: OpenInference span kinds (CHAIN/LLM/TOOL), LLM spans with token counts, tool spans, `session.id`, and real span annotations on verdict feedback. Dashboard panels (LLM/tokens/tool/sessions/annotations) populate on real runs.
- Cross-store reliability analyst is live: `get_phoenix_telemetry()` + `compute_detector_roi()` fuse Phoenix behavioral telemetry with Firestore confirmed accuracy; `/agent/detector-roi` and the upgraded `/agent/investigate` expose it. Verified on live data.
- Narration contradiction fixed (agent no longer claims a weight change when none occurred).
- Operator console fully implemented (Claude, not Codex): stack strip with Agent Builder pill, agent-run choreography (boot sequence + streamed steps + platform tags + live weight pulse), merged detector panel (Trust Leaderboard removed, drift arrows + self-calibration banner folded into Detector Influence), confidence-calibration card (`/agent/calibration`), human-review queue (`/agent/review-queue`), agent-vs-passive weight distinction (`weight_source` + "Agent override" badge), two-tier framing copy. Builds clean.
- Latency fixed: image/video pipeline now persists `latency_seconds`; old rows backfill from Phoenix root-span durations via `get_phoenix_root_latencies()`; display formats minutes (`2m 52s`).
- Agent run verified live (agent recalibrated a drifted detector with Phoenix MCP-labeled steps and honest narration). See the June 5 (continued) section in `CurrentHandoff.md` for the complete record, run order, and caveats.

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
- Gemini multi-key secret: `argusai-gemini-api-keys` (32 sanitized unique keys)
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
- Deployed Gemini key rotation across 32 sanitized keys via Secret Manager `argusai-gemini-api-keys`.
- Latency pass: final explanation generation now uses `gemini-3.1-flash-lite`, has a 30s timeout, audio sub-checks run concurrently, and video frame-heavy checks default to 2 frames.
- Audio model hardening: HF Space parser now reads the observed `prediction`/`confidence` response shape; local wav2vec2 weights were downloaded to `backend/models/wav2vec2-deepfake` for local demos and are ignored by git.
- Audio fusion now lets very high-confidence Gemini semantic listening drive the final audio verdict when wav2vec2/HF says authentic, while still showing the disagreement as evidence.
- `/arize/traces` endpoint reading Firestore first and x-ray logs as fallback for admin dashboard.
- Frontend Cloud Run deployment via `frontend/Dockerfile`.
- Frontend empirical reliability display, verdict feedback widget, admin global stats row, and Phoenix trace links.
- Admin stats consistency fixed: global totals now derive from Firestore `/analyses`, and the admin console polls every 15 seconds while open.
- Verdict cards show an inline Phoenix audit link, and official PDFs include trace ID/timestamp chain-of-custody footer.
- Admin panel includes the Firestore/Phoenix explanatory framing copy for judges.
- Phoenix MCP config fixed to use `PHOENIX_DASHBOARD_URL`.
- Local ADK agent package added at `agents/argusai_investigator`.
- ADK agent uses Gemini, ArgusAI backend tools, and Phoenix MCP via `npx @arizeai/phoenix-mcp`.
- Agent action endpoints added: detector reliability, similar cases, drift detection, detector recalibration, fact-check note, and human-review artifact.
- Fused Firestore outcomes with Phoenix telemetry for causal system self-calibration (June 4):
  - Advanced OpenInference tracing: mapped `CHAIN`, `LLM`, and `TOOL` span kinds, captured inputs/outputs, tracked `session.id`, and tagged LLM model names + prompt/completion/total tokens.
  - Span evaluations: Feedback widget writes real human-evaluation annotations to `/v1/span_annotations` of Phoenix by capturing and mapping `phoenix_span_id`.
  - Scraped Phoenix telemetry: Scrapes spans REST API to compute detector run counts, average latency, error rates, and model-fallback rates.
  - Cross-Store ROI Synthesis: `/agent/detector-roi` fuses Phoenix behavioral telemetry (latency, errors, runs) with Firestore outcome truth (confirmed accuracy, weight overrides) to rank detector efficiency and generate agent insights.
  - Upgraded Operator Console UI: Monospace styled Detector ROI Panel showing average tokens, latency, cost-efficiency tier, and custom agent insights. Activity feed scoped to system-level governance events; empty cards hide dynamically.
  - Upgraded Investigator Agent: `/agent/investigate` reads Phoenix telemetry, checks accuracy drift, recalibrates drifted detector weights (writes to Firestore), and narrates a reliability summary with concrete cost/latency/accuracy metrics.

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
- Local follow-up: the downloaded wav2vec2 model and HF Space both marked this exact clip authentic with high confidence, so the correct final verdict depends on the multi-signal fusion giving Gemini semantic listening priority when it is highly confident.

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
- Backend `/health` reports `gemini_key_count: 32`.
- Live `/analyze` returned a `phoenix_trace_id` and persisted an analysis to Firestore.
- Live backend revision after latency/model-routing work: `argusai-backend-00023-mtw`.
- Live frontend revision after Agent Builder/chain-of-custody work: `argusai-frontend-00005-r54`.
- Live `/stats` after the admin consistency fix returned matching Firestore global totals and media/verdict breakdowns; admin dashboard now polls every 15 seconds while open.
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
- Gemini Cloud Run key rotation is active with 32 sanitized keys.
- Audio voice authenticity is one signal, not the verdict. Modern generated audio can fool wav2vec2/HF; use Gemini semantic listening plus acoustic evidence for the final demo story when they disagree.
- Firestore global totals count unique analysis documents keyed by SHA-256. Re-uploading the exact same file may not increase the global total.
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
