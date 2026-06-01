# ArgusAI Architecture

Last updated: June 2, 2026.

Read `ContextFiles/CurrentHandoff.md` first for live deployment state. This file explains how the system fits together and why each major piece exists.

## High-Level Flow

Upload or Agent Builder request  
-> FastAPI backend  
-> media sniffing: image, video, or audio  
-> media-specific detector routing  
-> Phoenix root trace plus detector child spans  
-> detector health governor applies circuit-breaker/calibration policy  
-> reasoning engine combines only applicable usable evidence  
-> Gemini produces media-aware explanation and follow-up answers  
-> Firestore persists analysis, stats, feedback, and governor state  
-> React UI/admin/PDF/Agent Builder expose evidence, reliability, and audit trail

## Core Services

- Frontend Cloud Run: `https://argusai-frontend-1007754127412.us-central1.run.app`
- Backend Cloud Run: `https://argusai-backend-1007754127412.us-central1.run.app`
- Phoenix Cloud Run: `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`
- Firebase project: `argusai-8d9fe`
- GCP project: `argusai-497719`

Backend Cloud Run intentionally uses `max-instances=1` because sessions are currently in memory. Do not raise this until session state is externalized.

## Core Backend Files

- `backend/app/main.py` - FastAPI app, sessions, analysis endpoints, Agent Builder endpoints, stats, feedback, PDFs, Arize/admin endpoints.
- `backend/app/core/pipeline.py` - image/video orchestration, media routing, detector execution, report assembly, Phoenix span capture, Firestore persistence call.
- `backend/app/core/audio_pipeline.py` - standalone audio analysis pipeline and Firestore persistence call.
- `backend/app/core/observability.py` - OpenTelemetry/Phoenix setup with safe no-op fallback.
- `backend/app/core/health_governor.py` - detector health state, calibration divergence, Firestore-first persistence with local file fallback.
- `backend/app/core/firebase.py` - Firebase Admin SDK initialization; returns `None` gracefully when unavailable.
- `backend/app/core/analysis_store.py` - Firestore persistence, `/stats` support, `/arize/traces` support, feedback, Agent Builder history context.
- `backend/app/core/llm.py` - Gemini settings and multi-key rotation.
- `backend/app/core/llm_client.py` - Gemini semantic analysis, OSINT, explanation generation, and follow-up chat.
- `backend/app/reasoning/engine.py` - evidence weighting and final verdict synthesis.
- `backend/app/reports/pdf_official.py` - official PDF with chain-of-custody trace footer.

## Frontend Files

- `frontend/src/App.jsx` - upload flow, report cards, audio card, signal cards, feedback widget, admin panel, PDF download, Phoenix audit links.
- `frontend/src/styles.css` - visual system, signal cards, admin panel, reliability widgets, trace links.
- `frontend/Dockerfile` - Cloud Run frontend build; defaults to deployed backend and admin password.

## Media Routing

Image:

- spectral artifacts
- metadata
- noise pattern analysis
- lighting consistency
- semantic inconsistencies
- error level analysis
- OSINT verification

Video:

- frame extraction
- spectral artifacts on extracted frames
- metadata/container review
- semantic video review
- ELA on extracted frames
- OSINT verification
- temporal coherence
- optional embedded audio track extraction
- still-photo-only noise and lighting are hidden/not scored

Audio:

- audio deepfake/voice authenticity
- Gemini semantic audio listening fallback/context
- OSINT verification
- image-only signals hidden/not scored

The report includes `media_type`, and every signal includes `visible`. The frontend filters on `visible !== false`.

## Phoenix / Arize Layer

Phoenix tracing is configured through:

```env
PHOENIX_COLLECTOR_ENDPOINT=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces
PHOENIX_DASHBOARD_URL=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app
PHOENIX_PROJECT_NAME=argusai-forensics
ARIZE_HEALTH_GOVERNOR=1
```

The pipeline creates:

- root span: `argusai.analysis`
- detector child spans: `detector.<detector_id>`

Important span attributes:

- media type
- SHA-256
- verdict and certainty
- detector status/support/confidence/reliability
- detector latency
- circuit-breaker state and reason
- verdict influence percent
- calibration divergence state when present

Reports capture `phoenix_trace_id` and expose it in:

- verdict card
- expanded signal card details
- admin trace table
- official PDF metadata and footer
- Agent Builder responses
- Firestore `/analyses/{sha256}` records

## Firestore Layer

Firestore is persistent product memory. It complements Phoenix instead of replacing it.

Collections/documents:

```text
analyses/{sha256}
detector_stats/{detector_id}
stats/global
health_governor/state
```

Stored analysis fields include:

- timestamp
- SHA-256
- media type
- verdict and certainty
- Phoenix trace ID
- detector support/confidence/status/latency/visibility
- user feedback

`/stats` reads Firestore first and falls back to local x-ray logs.

`/arize/traces` reads Firestore first and falls back to local x-ray logs.

`/sessions/{session_id}/feedback` stores user confirmation/dispute and updates detector stats.

`build_history_context()` in `analysis_store.py` is used by Agent Builder endpoints to inject accumulated system memory.

## Agent Builder Surface

Google Cloud Agent Builder should configure two tools:

- `POST /agent/analyze`
- `POST /agent/chat`

These endpoints now return and/or use Firestore history context:

- total persisted analyses
- same-media analysis count
- detector reliability for the current report's signals
- recent same-media cases
- Phoenix trace ID

This is intentionally stronger than a generic Gemini wrapper. The agent has product memory and can explain reliability using accumulated data.

## Why Firestore + Phoenix

Firestore:

- mutable persistent intelligence
- fast stats for UI and agent
- survives Cloud Run restarts
- supports feedback loop and reliability scores

Phoenix:

- immutable audit trail for each decision
- trace-level evidence of detector execution
- observability proof for Arize judges
- chain-of-custody link for journalists/courts

Demo line:

> Firestore tells us how reliable each signal has been. Phoenix proves exactly what happened in this verdict.

## Deployment Notes

- Backend deploy command is in `ContextFiles/CurrentHandoff.md`.
- Frontend deploy command is in `ContextFiles/CurrentHandoff.md`.
- Phoenix deploy command is in `ContextFiles/CurrentHandoff.md`.
- Gemini multi-key rotation is deployed through Secret Manager secret `argusai-gemini-api-keys` with 35 keys.
- Firebase service account is deployed through Secret Manager secret `argusai-firebase-service-account`.
- Spectral model weights are downloaded from `gs://argusai-497719-models/models/argusai_best_weights.pth`.

Run before deploying:

```powershell
python -m compileall backend\app
cd frontend
npm run build
```
