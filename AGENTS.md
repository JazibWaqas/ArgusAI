# AGENTS.md — ArgusAI Working Instructions

Read `ContextFiles/CurrentHandoff.md` first, then `CLAUDE.md`. The handoff has the freshest deployment state, passwords, URLs, verified tests, and remaining manual work. `CLAUDE.md` explains the product strategy and why the Arize reliability governor is the winning angle.

Critical framing:

- ArgusAI is a forensic investigation platform, not a classifier.
- Evidence trail, not score.
- Arize Phoenix must be load-bearing: detector health events affect verdict influence.
- OSINT is the user-facing showstopper: provenance, sources, dates, research hops.
- Do not add more detectors or redesign the UI unless explicitly asked.
- **JUDGES ARE NOT OPENING AND TESTING the admin panel, nor do they get admin access.** They only watch the recorded demo video. At most, they will open the public site and browse standard user flows. Do not suggest adding password hints, exposing admin credentials in the UI, or modifying admin-panel security for judges. Everything they need is shown in the demo.


Current implemented hackathon additions:

- Phoenix/OpenTelemetry tracing in `backend/app/core/observability.py`.
- Detector health governor in `backend/app/core/health_governor.py`.
- Pipeline-level tracing and `pipeline_health` in `backend/app/core/pipeline.py`.
- Multi-modal image/video/audio routing with `media_type` and signal `visible` fields.
- Audio analysis endpoint now uses `AudioAnalysisPipeline`.
- Gemini semantic fallback for audio, video, and image when primary detector/model is unavailable or weak.
- Gemini fallback model behavior: primary `gemini-3.5-flash`, fallback `gemini-2.5-flash`.
- Cloud Run Gemini rotation is active through Secret Manager `argusai-gemini-api-keys` with 32 sanitized unique keys.
- Latency optimization pass implemented: final explanation generation is routed to `gemini-3.1-flash-lite` with a 30s timeout; audio sub-detectors execute concurrently via `asyncio.create_task`; video frame analysis extracts a default of 2 frames (configurable via `VIDEO_MAX_FRAMES`).
- Audio voice model handling was hardened: the HF Space parser now reads `prediction`/`confidence` responses, local wav2vec2 weights can run from `backend/models/wav2vec2-deepfake` for local demos, and high-confidence Gemini semantic listening can drive the final audio verdict when wav2vec2/HF disagrees.
- Video temporal coherence signal and graceful embedded audio-track signal.
- Gemini-grounded OSINT research agent and optional public-URL reverse-image enrichment in `backend/app/core/llm_client.py`.
- Upgraded OSINT detector output in `backend/app/detectors/osint.py`.
- Agent Builder endpoints in `backend/app/main.py`: `/agent/analyze` and `/agent/chat`.
- Arize health endpoint in `backend/app/main.py`: `/arize/health`.
- Arize trace feed in `backend/app/main.py`: `/arize/traces`.
- Firestore intelligence layer in `backend/app/core/firebase.py` and `backend/app/core/analysis_store.py`.
- Firestore-backed `/stats`, Firestore-backed `/arize/traces`, and `/sessions/{id}/feedback`.
- Admin dashboard stats are live and consistent: `/stats` derives global counts from Firestore `/analyses`, the admin console polls every 15s, and the main app refreshes stats after each completed analysis.
- Firestore is active on Cloud Run with Firebase project `argusai-8d9fe`.
- Agent Builder endpoints now query Firestore history context before responding, including total analyses, same-media counts, detector reliability, recent same-media cases, and `phoenix_trace_id`.
- Verdict cards and official PDFs surface Phoenix chain-of-custody links/trace IDs.
- Admin dashboard includes a concise Firestore/Phoenix framing line for judges.
- Arize badge, OSINT research UI, dynamic media UX, and password-gated admin dashboard in `frontend/src/App.jsx`.
- `.env.example` documents required env vars.
- `mcp/phoenix-mcp.json` is the official Phoenix MCP server template.
- `ContextFiles/AgentBuilderPhoenixSetup.md` documents Agent Builder and Phoenix MCP setup.
- Backend Cloud Run service is live at `https://argusai-backend-1007754127412.us-central1.run.app`.
- Frontend Cloud Run service is live at `https://argusai-frontend-1007754127412.us-central1.run.app`.
- Phoenix Cloud Run service is live at `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`.
- Admin password is `argusai2026`.
- Spectral weights are stored at `gs://argusai-497719-models/models/argusai_best_weights.pth`.
- Local self-hosted Phoenix is working through `docker-compose.phoenix.yml` at `http://localhost:6006`.
- Cloud Run backend points tracing to `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces`; Phoenix logs confirmed successful trace POSTs.

Next highest-leverage work:

1. Configure Agent Builder tools against `/agent/analyze` and `/agent/chat`.
2. Connect the Phoenix MCP server using `mcp/phoenix-mcp.json`.
3. Run the Pope puffer demo image end to end and confirm OSINT sources/dates.
4. Capture a prepared calibration-governor or spectral circuit-breaker trace for the demo.
5. Record the 3-minute demo.
6. Complete Devpost copy emphasizing “forensic investigation platform.”

Known caveat:

Cloud Run uses `min-instances=0` to avoid idle spend, so first requests may cold start. Switch backend and Phoenix to `min-instances=1` only near demo/judging if needed.

Backend `max-instances=1` is intentional because sessions are in memory. Do not raise it until session state is externalized.

Cloud Run cannot use `http://localhost:6006` for Phoenix. That local URL only works on the laptop. Cloud Run currently uses public self-hosted Phoenix at `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`.

Audio caveat: wav2vec2/HF is a real dedicated voice-authenticity signal, but it can misclassify modern Gemini-generated audio as authentic. Treat disagreement between wav2vec2, acoustic micro-signature, and Gemini semantic listening as honest evidence-trail behavior. For demos, pick audio where the final verdict is clear and explain the disagreement if it appears.

Stats caveat: analyses are persisted under `/analyses/{sha256}`. Re-uploading the exact same file updates that document rather than creating a new unique global analysis count.
