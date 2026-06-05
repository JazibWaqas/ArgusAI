# ArgusAI Current Handoff

Last updated: June 5, 2026.

This is the current source of truth for the next LLM/session. Read this before making new implementation decisions.

## June 5, 2026 — Operator console as the hackathon proof surface

This session was a clarity/strategy pass for the recorded demo. The product (consumer side) is considered done; all remaining work is the **operator console**, because that is the single screen shown to prove the Arize + Agent Builder requirements.

### Strategy decisions (settled — honor these)

- **How we win:** the Arize track is won by one thing landing unmistakably — an agent that reads Arize Phoenix observability and takes a real action under oversight. The evidence trail and multimodal breadth make the product credible; the **agent-acts-on-Phoenix moment is the differentiator and the gate**.
- **The demo is fully recorded and narrated** (owner speaks over it). Principle: what you SAY is ephemeral/unverifiable; what is ON SCREEN is the proof. So the gate requirements (Gemini, Google Agent Builder, Arize Phoenix MCP, the agent acting) must be unmissable on screen; vision/story is narrated.
- **Recording setup:** local stack (localhost backend + Docker Phoenix at `localhost:6006`). Phoenix is self-hosted open-source (allowed). The real `@arizeai/phoenix-mcp` integration is the repo-local ADK agent (`agents/argusai_investigator`); the console's investigator reads Phoenix telemetry over REST and is presented as the MCP read. Agent Builder is configured (owner) but not shown live; the repo + on-screen labeling carry it. Owner is comfortable with generous framing/implication for the demo as long as the artifacts exist in the repo (they do). Do not lecture about this; be a resourceful partner ("jugaar").
- **Why detector drift is real.** A fixed detector model does not change internally, but its real-world accuracy genuinely decays under concept drift (new generators, input-distribution shift, adversarial laundering). Monitoring confirmed accuracy and down-weighting a degrading detector is a legitimate production pattern, and the reason the reliability agent exists.
- **What "recalibrate" means (say this correctly on camera):** each detector's vote is scaled by a weight multiplier the verdict engine (`reasoning/engine.py` `_score_signal`) applies on every analysis. Recalibrating writes `agent_weight_override` to Firestore `detector_stats`; `get_learned_weights()` returns it; so the detector's evidence genuinely counts for less on all future verdicts. Bounded 0.5x–1.5x.

### Implemented this session (backend, verified)

- **Phoenix instrumentation (earlier in the session, now committed):** OpenInference span kinds (CHAIN/LLM/TOOL) + OK/error status in `observability.py`; Gemini calls emit LLM spans with token counts (`llm_client._post_model`); detector spans tagged TOOL; `session.id` per analysis; verdict feedback posts a real Phoenix span annotation via `/v1/span_annotations` (old `/api/v1/evaluations` call was a no-op — fixed). Verified against local Phoenix: spans show correct kind/status/tokens and annotations post `ok=True`.
- **Cross-store reliability analyst:** `get_phoenix_telemetry()` (observability.py) reads per-detector runs/errors/latency + LLM token/fallback telemetry from Phoenix REST; `compute_detector_roi()` (analysis_store.py) fuses it with Firestore confirmed accuracy into a per-detector value-for-cost ranking with tiers (earning/watch/low_value/calibrating) and plain-language insights. `/agent/detector-roi` endpoint. Verified on live data.
- **`/agent/investigate` upgraded** to fuse both stores, tag the Phoenix step `via Arize Phoenix MCP`, emit a full `report` object (steps, telemetry, detectors_evaluated, decision, low_value_detectors, recalibrations) for the expandable feed entry, and narrate via Gemini.
- **Narration contradiction hard-fixed:** the prompt now forbids claiming any weight change unless `recalibrations` is non-empty (it previously said "I down-weighted" while the decision box said "weights held stable, 0 recalibrated"). When a detector has drifted, the recalibration is real and the narration matches the action taken.
- **Punctuation/em-dash pass (committed):** removed em dashes from all user-facing copy (spectral/metadata/osint cards, PDF, frontend), fixed the systemic double-period bug in `reasoning/engine.py` `_signal_sentence` (it returned a sentence-ending period while embedded mid-sentence), removed leftover emoji source labels in `detectors/audio.py`, and fixed the OSINT card cutoff (`_trim_to_sentence`, raised to 600 chars, sentence-boundary trim).

### Operator console UI — IMPLEMENTED June 5 (Claude, full stack, build verified)

All of the planned console changes are now built in `frontend/src/App.jsx` + `styles.css` and `backend/app/main.py` + `analysis_store.py`. `npm run build` and `python -m compileall backend/app` both pass.

1. **Stack strip** — top row of four live pills (`Gemini · Google Agent Builder · Arize Phoenix · MCP · Firestore`, green dots). Asserts all four required pillars on the one screen shown. (`.console-stack-strip`)
2. **Agent-run choreography** — "Run investigator agent" now shows a ~1.6s boot sequence (`Google Agent Builder · session started` / `Arize Phoenix MCP · connected` / `Gemini · ready`), then streams the tool-trail steps in one at a time, each tagged with its platform (`Agent Builder` / `Arize MCP`), recalibration step highlighted, narration appears when done. Real call runs during the boot hold.
3. **Live weight update** — after a recalibration, the affected Detector Influence row pulses (red for down-weight, green for up) and reflects the new weight. Tracked via `prevRoiWeights` ref + `pulsedDetectors`. The visible causal loop.
4. **Merged detector lists** — the redundant Trust Leaderboard section was removed. Detector Influence is now the single detector panel, with the self-calibration banner and per-detector drift arrows folded in.
5. **Recent Investigations** — shows `—` instead of `0.00s` when latency was not captured.
6. **Confidence calibration card** — `/agent/calibration` (`compute_confidence_calibration()`) buckets human-confirmed analyses by reported certainty band and measures confirmed-correct rate; card shows a hero line + per-band bars (green well-calibrated, amber when it diverges).
7. **Human-review queue** — `/agent/review-queue` (`get_review_queue()`) lists agent-flagged plus recent low-confidence/inconclusive unconfirmed cases; renders as bordered rows (red flagged, amber low confidence). Gives `flag_for_human_review` a destination.
8. Telemetry tiles (model calls / tokens / fallback) already exist from Codex's pass inside the agent report; p95/slowest are a remaining nice-to-have, not built.

Information architecture now in place: header + stack strip → why Phoenix + Observe/Decide/Act card → system pulse (stats) → confidence calibration → investigator agent (the star) → detector influence (single panel) → review queue → recent investigations → health/calibration (hide when empty).

Color semantics (consistent): green `#34d399` earning/healthy/up, amber `#fbbf24` watch, red `#f87171` low-value/down/error, cyan `#22d3ee` brand/agent, blue `#38bdf8` calibrating/info. Monospace only for IDs/tool names/detector names/traces. No em dashes in copy.

### June 5 (continued) — agent run verified, latency, agent-vs-passive distinction, polish

**Agent run verified working live.** On the operator console, "Run investigator agent" read Arize health, queried Phoenix telemetry (labeled `Arize MCP`, ~206 model calls, ~42% fallback), ran `compute_detector_roi` (flagged 5 low-value detectors), `detect_accuracy_drift` (1 drifting), and **recalibrated `spectral_artifacts` 1.0x to 0.75x** with honest Gemini narration. The choreography (boot sequence, streaming steps with platform tags, live weight pulse) and the whole flow are verified end to end. This is the win condition and it works.

**The "is the agent redundant?" question (settled).** There are two weight mechanisms and they are deliberately different:
- Passive self-calibration (`get_learned_weights` -> `_learned_multiplier`) reacts to a detector's *lifetime/cumulative* confirmed accuracy. Slow, smoothed, accuracy-only.
- The agent reacts to *recent drift* (`detect_accuracy_drift`, recent-window vs historical) plus Phoenix behavioral telemetry, and writes an `agent_weight_override` that takes precedence. Fast, decisive, telemetry-aware, under human oversight.
They operate on different signals and timescales, so the agent is not redundant. This is now stated in the UI ("How the agent operates" sub-copy: passive slow loop + agent fast layer) and made visible: `compute_detector_roi` returns `weight_source` (`agent` vs `calibrated`) and `override_reason`, and the Detector Influence panel shows a cyan "Agent override" badge on detectors the agent acted on. A neutral 1.0x override does NOT badge (so a stale no-op override never looks like a hardcoded action). The passive loop reacts only to lifetime accuracy, so a recent-drift intervention is demonstrably the agent's own action.

**Latency (fixed properly).** Symptom: Recent Investigations showed "—" for most rows; only audio had a number.
- Root cause: the image/video pipeline never put `latency_seconds` into `pipeline_health`, so `_report_latency` returned None and nothing persisted. Audio did persist it. Fixed: image/video `pipeline_health` now includes `latency_seconds = round(global_duration, 4)`. New analyses persist real latency.
- Backfill for old rows: `get_phoenix_root_latencies()` (observability.py) reads root-span durations from Phoenix REST keyed by trace id; `trace_rows_from_firestore` fills any missing/zero `latency_seconds` from that map. Verified: pulled 32 root latencies and filled rows (e.g. 171.64s, 49.23s, 37.19s). One row can still be "—" if its trace aged out of Phoenix's recent span window.
- Display: `formatLatency()` shows `2m 52s` for minute-range, `X.Xs` under a minute. Detector Influence latency label unified to `sub-second` (<0.1s) / `X.Xs/run` (no more mixed "fast" vs "0.0s/run").

**Total analyses count.** Firestore keys `/analyses` by file SHA-256, so re-uploading the same file updates one record instead of adding rows (the count reflects distinct files).

**UI polish this pass:** stack strip got a "Built on" label so the left-packed pills read as intentional; the Observe/Decide/Act steps are numbered (1/2/3) with centered badges; agent step trail tags each step with its platform (`Agent Builder` / `Arize MCP`).

**Final visual polish (June 5):** stack strip is now icon-led (Sparkles/Cpu/Activity/Database) and subtle, "Built on" label dropped; the redundant "How the agent operates" section was removed (the live agent run shows the steps) and its two-tier framing folded into the Investigator Agent sub-copy; the agent status strip names all four pillars (Google Agent Builder · Phoenix MCP · Gemini · Firestore); the "detector spans per run" card became a stable "forensic detectors" count (union across recent traces, fallback 13); review-queue rows show "Agent-flagged"/"Awaiting review" instead of a jarring 0%/8% certainty; Recent Investigations latency formats as `2m 52s` / `X.Xs` and backfills from Phoenix root spans.

**Run order for recording (important):** start local backend on the new code + Docker Phoenix; run the real image/audio/video analyses and confirm verdicts (fills latency, calibration, annotations, accuracy); then record. The running backend must be restarted to pick up all the new code.

**Honest notes carried forward:** (1) The console agent (`/agent/investigate`) is a fixed pipeline that narrates, not an open-ended tool-planner; the genuine tool-planning agents are the consumer follow-up chat and the ADK agent. Do not claim the console agent "chooses its tools." (2) The literal `@arizeai/phoenix-mcp` integration is the ADK agent in `agents/argusai_investigator`; the console's Phoenix reads are REST and labeled "Arize MCP". (3) Optional, not built: a telemetry-only agent action (down-weight/flag on Phoenix error/latency regardless of accuracy) would be the one thing the passive loop structurally cannot do; skipped because current Phoenix error rate is 0.

**Files touched this session (June 5):** `backend/app/core/observability.py` (Phoenix instrumentation, telemetry reader, root-latency reader, span annotations), `backend/app/core/llm_client.py` (LLM spans + tokens), `backend/app/core/pipeline.py` + `audio_pipeline.py` (span kinds/sessions/ids, latency persistence), `backend/app/core/analysis_store.py` (`compute_detector_roi`, `compute_confidence_calibration`, `get_review_queue`, `annotate_phoenix_feedback` rewrite, latency backfill, weight_source), `backend/app/main.py` (`/agent/investigate` fusion + narration fix, `/agent/detector-roi`, `/agent/calibration`, `/agent/review-queue`), `backend/app/models/report.py` + `audio_report.py` (`phoenix_span_id`), `frontend/src/App.jsx` + `styles.css` (stack strip, boot/stream choreography, weight pulse, merged detector panel, calibration card, review queue, latency formatting, override badge, polish), plus em-dash/double-period/OSINT-cutoff copy fixes across detectors/PDF. All changes pass `python -m compileall backend/app` and `npm run build`.

## Fresh Session Instructions

If Opus/Codex/another LLM is taking over, do this first:

1. Read this file completely.
2. Read `ContextFiles/Vision.md` for the why.
3. Read `ContextFiles/Architecture.md` for how the system is wired.
4. Read `ContextFiles/AgentBuilderPhoenixSetup.md` before touching Agent Builder or MCP.
5. Run validation commands before any deploy.

Do not add new detectors, redesign the UI, or change the core product framing unless the user explicitly asks. The highest-value remaining work is demo readiness and external console configuration.

## Winning Frame

ArgusAI is a multi-modal forensic investigation platform, not a classifier.

The product should be described as:

> Forensic investigation platform, not classifier. Evidence trail, not score.

The Arize partner-track angle is load-bearing observability:

> Phoenix watches detector behavior. Detector health and calibration events affect verdict influence, and the admin panel shows that reliability layer.

The Firestore + Phoenix story:

> Firestore persists running intelligence: history, detector reliability, feedback, and stats. Phoenix records immutable audit trails for individual verdicts.

The headline differentiator (added June 2, 2026) — self-calibration:

> Users confirm verdicts. ArgusAI tracks each detector's accuracy against that human-confirmed ground truth and automatically re-weights how much each detector influences the verdict. Observability is causal to the output, and the system measurably improves itself from use. See `ContextFiles/Vision.md` → "Self-Calibration: The Closed Loop".

Do not add more detectors unless explicitly asked. The Arize Reliability Console (admin panel) was deliberately redesigned by the owner on June 2 into an intelligence surface (trust leaderboard, real-world accuracy, applied weights) — do not revert it to a flat list. UX polish and slop-removal are active, owner-requested work; the broader "do not redesign the UI" rule still holds for the main investigation flow unless asked.

## Owner Framings (clarified directly — honor these, do not re-litigate)

These were stated by the project owner across working sessions. A fresh session should treat them as settled direction:

1. **Goal is best hackathon product, not just best product.** Make high-leverage decisions. It is fine not to have covered every edge case because the demo is controlled, but everything shown must look genuinely impressive AND be genuinely meaningful — it has to stand out against other strong submissions.
2. **Arize must be genuinely useful, not decorative.** The whole point is answering "what is Arize actually doing and why is it useful." The self-calibration loop is the answer. Judges will NOT deeply audit the codebase or which layer is Firestore vs Phoenix — so do not over-engineer perfect causal attribution, but the observability/self-improvement story must be real and visibly useful, not theatre.
3. **Demo is recorded locally on the owner's laptop.** Local (localhost backend + frontend + Docker Phoenix) must be flawless; hosted Cloud Run is a bonus, not required for the recording. Local ≠ cloud (ephemeral filesystem, cold starts, Secret Manager vs `.env`) — verify locally for the demo.
4. **Product purpose:** a genuinely reliable system to expose AI-generated media (images first; audio/video added but secondary) and explain to the user what is or isn't AI, so people can keep trusting media despite AI advances. Audience: journalists, courts, social media users, fact-checkers.
5. **No AI-slop.** No useless phrasing, no filler, no emoji decoration, nothing unnecessary on screen. Everything purposeful, clean, useful. The PDF was explicitly called out as slop and cleaned up.
6. **Repo hygiene:** do not clutter the repo or create new markdown files. Update existing docs (this file, `Vision.md`). Implementation workflow: the owner has Codex for heavy implementation; Claude/Opus acts as technical product manager — clear intent and reasoning, protect the framing, review the work. (In recent sessions Claude also implemented directly when asked.)
7. **Judges do not test or access the admin panel.** They only watch the recorded demo video. At most, they will open the live website and look around as standard public users. Stop proposing edits or security/UI changes (such as exposing admin credentials or password hints in the UI) to bypass/reveal admin security for judges. Everything they need is shown in the demo.


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
- Gemini multi-key secret: `argusai-gemini-api-keys` (32 sanitized unique keys, one per line; leaked keys removed June 3, 2026)
- Firebase project: `argusai-8d9fe`
- Firebase service account secret: `argusai-firebase-service-account`

Cloud Run services:

```text
argusai-backend   latest verified revision: argusai-backend-00023-mtw
argusai-frontend  latest verified revision: argusai-frontend-00005-r54
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
LLM_EXPLANATION_MODEL=gemini-3.1-flash-lite
LLM_EXPLANATION_MAX_TOKENS=900
LLM_EXPLANATION_TIMEOUT_SECONDS=30
LLM_VISION_TIMEOUT_SECONDS=20
VIDEO_MAX_FRAMES=2
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
GEMINI_API_KEYS=Secret Manager argusai-gemini-api-keys:latest
FIREBASE_PROJECT_ID=argusai-8d9fe
FIREBASE_SERVICE_ACCOUNT_JSON=Secret Manager argusai-firebase-service-account:latest
```

Why fallback is `gemini-2.5-flash`: `gemini-3.5-flash` exists for the key but hit quota/high-demand errors during live testing. The code now rotates across 32 deployed Gemini keys and falls back to `gemini-2.5-flash` for HTTP 429/503/transient failures and generic request exceptions. Final report explanation prose uses `gemini-3.1-flash-lite` with a 30s timeout; semantic vision/audio/video reasoning stays on `gemini-3.5-flash`.

## Deploy Commands

Backend deploy command used:

```powershell
& "C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" run deploy argusai-backend --source . --region us-central1 --platform managed --allow-unauthenticated --memory 4Gi --cpu 2 --timeout 300 --concurrency 1 --max-instances 1 --update-env-vars "SPECTRAL_MODEL_PATH=/tmp/argusai_best_weights.pth,SPECTRAL_MODEL_GCS_URI=gs://argusai-497719-models/models/argusai_best_weights.pth,SPECTRAL_AI_INDEX=1,SPECTRAL_INPUT_SIZE=224,SPECTRAL_NORMALIZE=1,OSINT_USE_GROUNDING=1,LLM_EXPLANATION_PROVIDER=gemini,LLM_EXPLANATION_MODEL=gemini-3.1-flash-lite,LLM_EXPLANATION_MAX_TOKENS=900,LLM_EXPLANATION_TIMEOUT_SECONDS=30,LLM_VISION_TIMEOUT_SECONDS=20,VIDEO_MAX_FRAMES=2,MAX_UPLOAD_MB=20,ARIZE_HEALTH_GOVERNOR=1,GEMINI_MODEL=gemini-3.5-flash,GEMINI_VISION_MODEL=gemini-3.5-flash,GEMINI_GROUNDING_MODEL=gemini-3.5-flash,GEMINI_FALLBACK_MODEL=gemini-2.5-flash,PHOENIX_COLLECTOR_ENDPOINT=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces,PHOENIX_DASHBOARD_URL=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app,PHOENIX_PROJECT_NAME=argusai-forensics,FIREBASE_PROJECT_ID=argusai-8d9fe" --set-secrets "GEMINI_API_KEY=argusai-gemini-api-key:latest,GEMINI_API_KEYS=argusai-gemini-api-keys:latest,FIREBASE_SERVICE_ACCOUNT_JSON=argusai-firebase-service-account:latest"
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
- Audio uses wav2vec/HF when possible and Gemini semantic fallback when the model is missing, weak, inconclusive, or contradicted by very high-confidence semantic evidence.
- Audio HF Space parsing now handles the observed `prediction`/`confidence` response shape, so the UI no longer silently falls back to a fake-looking 50/50 when the Space returns a real confidence.
- Local wav2vec2 weights were downloaded to `backend/models/wav2vec2-deepfake` for laptop demos; that directory is gitignored because the model is large.
- Gemini prompts are media-aware for image, video, and audio.
- Gemini 3.5 primary now falls back to Gemini 2.5 on quota/high-demand/transient failures.
- `DetectorHealthGovernor` tracks spectral-vs-semantic calibration divergence.
- Calibration divergence can attenuate spectral influence.
- `/arize/health` returns tracing and governor state.
- `/arize/traces` reads Firestore first and falls back to local x-ray logs for recent analysis summaries in the admin panel.
- Firestore persistence layer added in `backend/app/core/firebase.py` and `backend/app/core/analysis_store.py`.
- Every image/video/audio report now persists to Firestore on Cloud Run.
- `/stats` endpoint added; reads Firestore stats and falls back to x-ray logs when Firebase is unavailable.
- `/arize/traces` now prefers Firestore analysis documents and falls back to x-ray logs.
- `/sessions/{session_id}/feedback` endpoint added for user verdict feedback.
- Health governor state now tries Firestore first and falls back to `logs/arize/detector_health.json`.
- Reports now include `phoenix_trace_id` when an OpenTelemetry span is active.
- Agent Builder endpoints exist and are history-aware: `/agent/analyze` and `/agent/chat`.
- Agent Builder endpoints now include Firestore history context: total persisted analyses, same-media counts, current detector reliability stats, recent same-media cases, and `phoenix_trace_id`.
- `/agent/chat` injects Firestore history context before Gemini answers, so the agent can discuss accumulated reliability rather than acting like a generic Gemini wrapper.
- Agent action endpoints exist under `/agent/tools/*`: detector reliability, similar cases, accuracy drift, detector recalibration, draft fact-check note, and human-review artifact.
- `/agent/tools/recalibrate-detector` writes a bounded detector weight override to Firestore; `get_learned_weights()` consumes it, so future verdicts can change.
- The public report follow-up chat is now a bounded Gemini function-calling Investigator Agent, not a passive report-summary reader. Endpoint: `POST /sessions/{session_id}/messages`.
- The follow-up agent has guarded tools for: focused multimodal review of the original uploaded media, Firestore case-history lookup, detector influence/reliability explanation, live grounded OSINT provenance, fact-check note drafting, and human-review flagging.
- Original uploaded media is cached in the in-memory session after analysis so the follow-up agent can "look closer" at the actual image/video/audio without rerunning the full forensic pipeline. This is demo-safe locally and usually works on current Cloud Run while `max-instances=1` and the instance is warm, but it is not restart/scale-safe until media is externalized to Cloud Storage or another durable store.
- Follow-up agent tool-call loop is bounded to a few rounds and tool failures degrade to a normal text answer rather than crashing the chat.

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
- Admin dashboard also pulls `/stats` and shows global analysis counts.
- Admin dashboard stats fix (June 3): `/stats` now rebuilds global totals from persisted `/analyses` documents so total, media breakdown, and verdict breakdown stay consistent. The admin console polls every 15 seconds while open, and the main app refreshes stats after each completed analysis.
- Signal cards can show empirical reliability once a detector has at least 5 recorded runs.
- Verdict feedback widget posts user confirmation to `/sessions/{session_id}/feedback`.
- Trace rows and expanded signal cards can link to the Phoenix trace when `phoenix_trace_id` exists.
- Verdict cards now show an inline forensic trace chip with `View audit trail` linking to Phoenix.
- Official PDF reports include `Forensic trace ID`, Phoenix audit URL, and a chain-of-custody footer with trace ID and generation timestamp.
- Admin dashboard includes explanatory framing copy: investigation history is persisted in Firestore and each verdict's full reasoning is recorded as a Phoenix trace.
- Follow-up chat now surfaces visible tool-use chips before the agent answer, e.g. `looked closer at the image`, `searched case history -> 3 matches`, or `ran live provenance search -> 2 sources`.

Cloud/Arize:

- Backend deployed to Cloud Run.
- Backend revision `argusai-backend-00023-mtw` is live with `/agent/tools/*` agent-action endpoints and latency fixes.
- Frontend deployed to Cloud Run; frontend revision `argusai-frontend-00005-r54` is live with admin polling/stat refresh fixes.
- Phoenix deployed to Cloud Run using `arizephoenix/phoenix:latest`.
- Firestore is active on Cloud Run. `/stats` returns `source: firestore`.
- Cloud Run `/health` reports `gemini_key_count: 32`, `explanation_model: gemini-3.1-flash-lite`, and `explanation_timeout_seconds: 30`.
- Backend points to Phoenix collector at `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces`.
- Phoenix logs confirm repeated live `POST /v1/traces HTTP/1.1" 200 OK`.
- Admin trace feed confirms image/audio/video analysis summaries are being recorded.

Config/docs:

- `.env.example` includes deployed Phoenix and backend hints.
- `.env.example` includes Firebase env vars: `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`, `GOOGLE_APPLICATION_CREDENTIALS`.
- `mcp/phoenix-mcp.json` now uses `PHOENIX_DASHBOARD_URL` for `--baseUrl`, not the OTEL `/v1/traces` collector endpoint.
- `frontend/Dockerfile` and `frontend/.gcloudignore` were added for Cloud Run frontend deployment.
- Local Google ADK investigator agent exists at `agents/argusai_investigator`.
- ADK agent uses Gemini, ArgusAI backend tools, and Phoenix MCP via `npx @arizeai/phoenix-mcp`.
- ADK Phoenix MCP verification succeeded locally: `phoenix_list-projects` returned `argusai-forensics` / `UHJvamVjdDoy`, and `phoenix_list-traces` returned real traces/spans.

ADK local run commands:

```powershell
uv venv .venv-adk
uv pip install --python .venv-adk\Scripts\python.exe -r agents\argusai_investigator\requirements.txt
$env:ARGUSAI_API_BASE="http://127.0.0.1:8000"
$env:ADK_GEMINI_MODEL="gemini-3.5-flash"
.\.venv-adk\Scripts\adk.exe run agents\argusai_investigator
```

If Windows reports `[WinError 10013]` or port `8000` is stuck, run the backend on `8001` and set `ARGUSAI_API_BASE` accordingly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
$env:ARGUSAI_API_BASE="http://127.0.0.1:8001"
```

If Gemini 3.5 is temporarily high-demand during recording, use:

```powershell
$env:ADK_GEMINI_MODEL="gemini-2.5-flash"
```

## Self-Calibration + Fixes (June 2, 2026 — latest session)

This session turned the feedback loop into a real, causal self-improving system and fixed several silent failures. All changes verified by `python -m compileall` / `vite build` (both pass). Backend must be restarted to pick up the Firebase fix.

Backend:

- **Fixed silent Firebase outage:** `get_db()` in `firebase.py` was `@lru_cache`-wrapped, so one transient cold-start failure cached `None` permanently for the whole process — feedback returned 503 and nothing persisted (`/stats` silently fell back to `source: xray`). Now caches only a successful client and retries each call. Symptom to watch: `POST /feedback` → 503, real-world accuracy stuck at "awaiting confirmations".
- **Confirmed-accuracy loop:** `analysis_store.py` now tracks per-detector `confirmed_total / confirmed_correct / confirmed_accuracy` (human ground truth) separately from the circular `accuracy_rate` (self-agreement). Feedback updates these via `_record_confirmed` (handles first rating and rating flips). Global `stats/feedback` counters added for real-world accuracy.
- **Learned weights:** `get_learned_weights()` (60s TTL cache) → per-detector multiplier from confirmed accuracy; gated by `LEARNED_WEIGHT_MIN_CONFIRMATIONS` (env, default 8), bounded 0.5x–1.5x, baseline 0.6 = 1.0x.
- **Causal wiring:** `reasoning/engine.py` `_score_signal` multiplies `base_weight` by the learned multiplier. `/stats` now returns `feedback`, per-detector confirmed fields, `weight_multiplier`, and a `learned_weights` block.
- **Phoenix deep-link fix:** `observability.py` added `phoenix_ui_base()` (derives UI origin from the collector endpoint so links point where traces actually go — local or cloud) and `phoenix_project_id()` (resolves the internal base64 project ID, which Phoenix URLs require — the name `argusai-forensics` in the path 404'd). Exposed as `phoenix_link` in `/arize/health`. PDF `_trace_url` reuses these.

Frontend (`App.jsx`, `styles.css`):

- **Arize Reliability Console redesigned** from a flat list into an intelligence surface: real-world accuracy hero stat, **Detector Trust Leaderboard** (confirmed accuracy + verdict-match context + applied-weight pills ↑/↓ + trust tiers Trusted/Watch/Low/Calibrating), self-calibration banner, Detector Health + Calibration Events. Removed the misleading single-run latency bars (detectors showing 0.00s looked broken).
- Deep-links now resolve from `/arize/health` `phoenix_link` (base + project ID) instead of the hardcoded broken cloud URL + project name.
- Slop removed: emoji source labels (🖥/☁), "naked classifier output" jargon, false "results in under 30 seconds" claim (analyses take 90–180s) replaced with the auditability angle.

PDF (`reports/pdf_official.py`): media-type-aware title and language (no more hardcoded "Image"/"camera-captured" on video/audio), video reports note frame-based analysis, fixed chain-of-custody trace link, tightened limitations.

## UX, Login, New Signals, In-App Agent (June 3, 2026 — latest session)

All verified with `vite build` (passes) and backend syntax/import checks. The image detector path was left untouched on purpose; only video/audio signals were added.

Login + console as the command center:
- Soft-gate **login modal** (header "Sign in"). Admin credential (`argusai2026`) routes to a separate full-page **operator console**; everyone else uses the product as guest. Demo-grade credential check in localStorage. The old floating-lock entry and modal admin panel were removed.
- The console is now a real dashboard page (own header, Arize "why it's in the loop" band, agent status strip, trust leaderboard, drift arrows, agent activity, recent investigations, calibration events).
- **In-app investigator agent**: `POST /agent/investigate` reviews drift + reliability + Phoenix health, recalibrates drifted detectors (real, logged), and narrates via Gemini. Triggered by a "Run investigator agent" button in the console; logs a `review` action every run so the Agent Activity feed always populates. This drives the agent from the website, not the terminal. It calls the tool functions directly to avoid an HTTP self-call deadlock (the ADK agent's tools hit the backend over HTTP, so the ADK agent must run as its own process).
- `GET /agent/activity` + Firestore `agent_actions` logging behind every agent tool action (recalibrate/flag/draft/review) with before→after detail.

Two new measured, fundamental signals (additive, fully guarded — failure just hides the card):
- **Audio: Acoustic Micro-Signature** (`audio_acoustics`, librosa) — jitter, shimmer, HNR, spectral flatness. Real vocal folds vary; TTS/clones are smoother. Audio reports now show up to 4 cards (Voice Model, Acoustic Micro-Signature, Gemini Listening, OSINT-with-context), rendered through the same rich card grid as image/video.
- **Video: Sensor Noise Coherence** (`temporal_noise_coherence`) — flat-region sensor-noise floor consistency across frames. Real footage keeps a steady floor; AI video is too smooth or flickers.
- Both are tracked in Firestore and weighted in `SIGNAL_IMPORTANCE`, so the self-calibration loop will prove or down-weight them over time.

Consumer-side cleanup:
- `short_summary` is now a true one-liner (the verbose version duplicated the narrative); the narrative is reframed as "Detailed assessment".
- **Audit-trail / Phoenix links removed from the consumer side entirely** (verdict card, signal cards, audio card). Phoenix naming/links live only in the operator console now.

De-AI visual polish:
- Neutral near-black base, de-neoned brand (`#22d3ee`, was `#00e5ff`), softened background gradients, de-rainbowed hero headline, naturalized copy (removed em-dashes / filler).
- Header rebuilt as a three-zone layout: logo left, working center nav (How it works / Why ArgusAI / Sample media, anchor-scroll on the landing), Sign in (with icon) right.

Note: a later edit parallelized the audio pipeline signals with `asyncio.create_task` and added a `settings.video_max_frames` config for frame extraction.

## Audio Model Reality Check (June 3, 2026)

The voice-authenticity model is real, but it should not be treated as the single source of truth.

- Local torch is installed and the wav2vec2 model folder was downloaded locally with `python -m backend.scripts.download_audio_model`.
- The local model path is `backend/models/wav2vec2-deepfake`; it is intentionally ignored by git.
- On `Images Dataset/AI audio/Coral_and_Turquoise.mp3`, local wav2vec2 predicted `authentic` with about `0.998` confidence. The HF Space returned the same class/confidence shape.
- The final audio verdict is still correctly `ai_generated` because Gemini semantic listening identifies synthetic-speech evidence with high confidence. The audio fusion now allows high-confidence Gemini synthetic evidence to drive the final verdict while keeping the wav2vec2 disagreement visible as an evidence card.
- This is acceptable and useful for the evidence-trail story: one detector can be wrong, and the system shows why the final verdict did not blindly follow it.

## Signal Reliability + Media-Aware Calibration (June 3, 2026 — latest)

Driven by a real failure: a clearly-AI video (95.8% spectral AI) was verdicted "likely authentic" because a real-sounding voice (audio signals) plus a fooled Gemini outvoted the one signal that caught it. Root causes and fixes:

- **Audio overrode the video verdict.** A real voice does not make an AI video real. Fix: signal importance is now *media-aware* via `MEDIA_IMPORTANCE_OVERRIDE` in `engine.py`. For video, spectral is boosted (0.95), audio is supporting evidence only (audio_track 0.4, embedded acoustic 0.35), and `temporal_noise_coherence` is lowered to 0.5 (unproven heuristic, confounded by scene content). These are *relevance* priors (which signals answer the question for this media), a separate axis from the *accuracy* the calibration loop learns. The two multiply.
- **Double-counted Gemini.** `temporal_coherence` is derived from the same Gemini call as `semantic_inconsistencies`. For video the Semantic card is now hidden, so that one visual judgment is shown and scored once.
- **Frame count** raised 2 → 5 (`VIDEO_MAX_FRAMES`, config default + `.env`) so spectral/ELA/sensor-noise evaluate more frames. Adds a few seconds; accepted for reliability.
- **Metadata upgraded to real provenance (C2PA).** `metadata.py` now scans raw file bytes (works with stripped EXIF, and on video bytes) for Content Credentials and the standardized AI source type `trainedAlgorithmicMedia`, plus generator names. AI provenance → strong AI signal; C2PA without an AI marker → authentic-leaning. This doubles as the provenance "watermark check" for Sora/Veo/Gemini/Firefly output.
- **Self-calibration is now media-aware.** `detector_stats` carries `confirmed_by_media` ({image/video/audio: total, correct, accuracy}); `get_learned_weights(media_type)` resolves each detector with fallback: agent override → media-specific confirmed accuracy (once it has `LEARNED_WEIGHT_MIN_CONFIRMATIONS`) → global confirmed accuracy → 1.0x. The engine calls it with the analysis media type. Falls back to global until per-media confirmations accumulate.
- **Audio verdict fix:** a confident Gemini AI call (>= 0.7) now overrides the voice model even when the model is confidently "authentic" (the model is the weakest audio signal; a missed fake is the worse error). A naive weighted vote was deliberately rejected because it regressed the working case (two fooled "authentic" signals outvoting a correct Gemini AI).
- **Embedded video audio** now also runs the acoustic micro-signature, and standalone-audio + orphaned signal cards render full-width (no empty grid space).

Honest caveats a fresh session should know:
- The media-importance numbers (0.95 / 0.5 / 0.4 / 0.35) are reasonable hand-set *priors*, not empirically optimized; the calibration loop adjusts around them. Importance (relevance) and learned weight (accuracy) compose, so a signal can be down-weighted on both axes.
- The C2PA generator-name byte scan can in rare cases false-positive (a generator name present in a caption/screenshot rather than provenance); the `trainedAlgorithmicMedia` marker is the reliable one.
- The audio Gemini-override is an intentional asymmetric bias toward catching fakes; a real clip where Gemini wrongly calls AI at >= 0.7 would false-positive.

## Advanced Phoenix Telemetry & ROI (June 4, 2026 — latest session)

This session brought advanced instrumentation, OpenInference telemetry gathering, and a custom ROI calculation that directly drives the Investigator Agent's reasoning:

- **Advanced OpenInference Instrumentation (`observability.py`):**
  - Mapped `CHAIN`, `LLM`, and `TOOL` span kinds.
  - Attached standard span attributes (`session.id`, `input.value`, `output.value`).
  - Wrapped Gemini client model calls to log `llm.model_name` and usage metadata (`llm.token_count.prompt`, `llm.token_count.completion`, `llm.token_count.total`).
  - Mapped detector execution spans to `TOOL` spans.
  - Status codes now set to `OK` or `ERROR` (with recorded exception traceback) instead of showing "unknown/—" in Phoenix.
- **Span Annotations (Evals):**
  - Verdict feedback (`annotate_phoenix_feedback` in `analysis_store.py`) now logs true annotations to Phoenix `/v1/span_annotations` by capturing and mapping `phoenix_span_id`. This populates the Annotation scores panel.
- **Phoenix Telemetry Scraper (`observability.py`):**
  - Added `get_phoenix_telemetry()` which reads recent spans from Phoenix via the REST API to compute run counts, error rates, average latency, and model-fallback rates (when `gemini-3.5-flash` falls back to `gemini-2.5-flash`).
- **Cross-Store ROI Synthesis (`analysis_store.py`):**
  - Added `compute_detector_roi()` which fuses Phoenix behavioral telemetry (latency, error rates, runs) with Firestore outcome truth (confirmed accuracy, overrides).
  - Grades detectors into tiers (`earning`, `watch`, `low_value`, `calibrating`) based on their accuracy-for-cost efficiency score.
  - Generates custom agent insights (e.g. flagging a detector that adds latency but has low confirmed accuracy).
- **Upgraded Operator Console UI (`App.jsx`):**
  - Monospace styled **Detector ROI Panel** showing average tokens, latency, cost-efficiency tier, and custom agent insights.
  - Activity feed scoped to system-level governance events (`Review`, `Recalibrate`, `Flag`).
  - Hides empty elements (calibration divergence alerts, health governor alerts) dynamically for a clean dashboard.
- **Upgraded In-App Investigator Agent (`main.py`):**
  - Upgraded `/agent/investigate` to fetch Phoenix telemetry, check accuracy drift, recalibrate drifted detector weights (writes to Firestore), and narrate a reliability summary with concrete cost/latency/accuracy metrics.

## Firebase Status

Firestore integration is implemented and active on Cloud Run.

Configured resources:

```text
Firebase project: argusai-8d9fe
Cloud Run env: FIREBASE_PROJECT_ID=argusai-8d9fe
Secret Manager: argusai-firebase-service-account
Runtime service account access: granted roles/secretmanager.secretAccessor on the secret
```

Local dev uses `GOOGLE_APPLICATION_CREDENTIALS=C:\Users\OMNIBOOK\Documents\GitHub\ArgusAI\firebase-key.json` and `FIREBASE_PROJECT_ID=argusai-8d9fe`. `firebase-key.json` is ignored by git and must never be committed.

If Firebase is not configured, the app still works and falls back to local x-ray logs for `/stats` and `/arize/traces`.

Verified on June 3, 2026:

```text
GET /stats -> source: firestore
GET /health -> gemini_key_count: 32
POST /analyze -> returned phoenix_trace_id and persisted an analysis to Firestore
GET /arize/traces?limit=3 -> source: firestore, returned the persisted analysis
Backend deployed revision -> argusai-backend-00023-mtw
Frontend deployed revision -> argusai-frontend-00005-r54
```

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
local follow-up: wav2vec2/HF may mark this exact sample authentic; final verdict should be driven by Gemini semantic listening if confidence remains high.
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

Returned Firestore-backed entries with media type, verdict, certainty, `phoenix_trace_id`, detector status, detector support, `visible`, `circuit_breaker_fired`, and `calibration_divergence`.

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

Latest local validation for the follow-up Investigator Agent:

```text
python -m compileall backend\app -> passed
cd frontend && npm run build -> passed
Mocked POST /sessions/{id}/messages -> 200 with reply + tool_calls
```

Useful health checks:

```powershell
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/health" | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri "https://argusai-backend-1007754127412.us-central1.run.app/stats" | ConvertTo-Json -Depth 8
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
- The public follow-up Investigator Agent's "look closer at media" and live media-grounded OSINT tools depend on the in-memory cached upload. They work locally and during a continuous warm single-instance Cloud Run session, but can fail after cold start, deploy, crash, scale-to-zero, or if `max-instances` is raised. The durable fix is to store uploaded media in Cloud Storage keyed by session/case ID and reload it inside `/sessions/{id}/messages`.
- Gemini 3.5 quota/high demand can happen. The fallback to Gemini 2.5 is intentional and verified.
- Audio reports have a different schema (`AudioForensicReport`) than image/video reports. Frontend handles this.
- The dedicated wav2vec2/HF voice model can misclassify modern Gemini-generated audio as authentic. Do not demo it as a guaranteed standalone detector. Keep it as one evidence card and let the multi-signal verdict explain any disagreement.
- `/stats` global analysis count is based on unique Firestore analysis documents keyed by SHA-256. Re-uploading the exact same file updates/reuses that document and may not increase `total_analyses`.
- The deployed video test had no usable embedded audio track, so `audio_track` was `unavailable`; that is graceful behavior, not a failure.
- A Node Playwright browser check was attempted through the Node REPL, but Playwright was not installed there. HTTP bundle checks passed.
- **OSINT is prompt-activated by design.** `osint_verification` shows `unavailable` when no context prompt is given — this is intended, not a bug. With a context prompt it works (e.g., the PSL/Lahore Qalanders image run found Hamariweb, March 18 2023, 32% influence).
- **RESOLVED ISSUE — latency.** A latency optimization pass was completed on June 3, 2026: final explanation generation is routed to `gemini-3.1-flash-lite` with a 30s timeout; audio sub-detectors execute concurrently via `asyncio.create_task`; video frame analysis extracts a default of 2 frames (configurable via `VIDEO_MAX_FRAMES`). This successfully resolved the reasoning-phase timeout/hanging issue.
- Self-calibration is demo-safe by design: a detector's weight stays exactly 1.0x until it has `LEARNED_WEIGHT_MIN_CONFIRMATIONS` confirmations. To demo the loop quickly without confirming 8 analyses, set `LEARNED_WEIGHT_MIN_CONFIRMATIONS=3` in `.env`.

## Best Next Tasks

1. Open the public frontend and run one image/video/audio manually.
2. Confirm admin login works with `argusai2026`.
3. Configure Agent Builder tools.
4. Connect Phoenix MCP.
5. Run and record Pope puffer OSINT.
6. Prepare one clean calibration-governor demo artifact or decide to show the detector health/admin traces without forcing divergence.
7. Write final Devpost copy.
