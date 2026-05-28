# CLAUDE.md — ArgusAI Source of Truth

This file is the single source of truth for the ArgusAI project. Read this before touching any code.
Every strategic decision, feature choice, UX decision, and implementation priority is captured here.

---

## What This Project Is

**ArgusAI** is a forensic investigation platform for image verification. It determines whether an image
is AI-generated or authentic by running seven parallel forensic detectors and combining their outputs
into a weighted evidence verdict with a plain-language explanation.

The critical framing distinction: **this is not a classifier. It is a forensic investigation platform.**
Every other deepfake detector gives you a confidence score. ArgusAI gives you an evidence trail —
specific named sources, detector-by-detector reasoning, and a research agent that investigates the
image's provenance on the live web. This framing must be preserved in all copy, demo narration, and UI text.

---

## Hackathon Context

**Competition**: Google Cloud Rapid Agent Hackathon — Arize Partner Track  
**Deadline**: June 11, 2026 (submissions close 2:00 PM PT)  
**Judging Period**: June 22 – July 6, 2026  
**Prizes**: $5,000 / $3,000 / $2,000  
**Target**: First place

**Hard Requirements (non-negotiable):**
- Agent built with Gemini and Google Cloud Agent Builder
- Meaningful Arize MCP integration (not just logging)
- Live hosted URL (Google Cloud Run)
- Public GitHub repo with MIT License file visible in About section
- 3-minute YouTube demo video
- All code using Google Cloud services — no competing inference providers

**Judging Criteria (equal weight):**
1. Technological Implementation
2. Design / UX
3. Potential Impact
4. Quality / Creativity of the Idea

**Key insight about winning**: The Arize integration must be *load-bearing*, not decorative.
Removing it should visibly break or degrade the product. Judges are senior Arize employees who
will immediately recognize shallow logging versus meaningful observability.

---

## Current State of the Codebase (What Is Already Built)

The project is **fully functional locally**. This is not a prototype — it works end-to-end.

### Backend (FastAPI, Python)
- `backend/app/main.py` — FastAPI app, session management, all HTTP endpoints
- `backend/app/core/pipeline.py` — Main analysis pipeline. Runs all 7 detectors in parallel with
  `asyncio.gather`. Already collects per-detector metrics (latency, status, confidence) into an
  `xray_metrics` dict and writes it to `logs/xray/` as JSON. **This is the telemetry feed that
  Arize Phoenix will consume.**
- `backend/app/core/llm_client.py` — Multi-provider LLM client (Gemini primary). Handles
  vision analysis, OSINT query generation, OSINT synthesis, grounded search, and report narrative.
  Has key rotation and fallback model logic.
- `backend/app/core/llm.py` — LLM settings / configuration class
- `backend/app/core/config.py` — App settings from env vars
- `backend/app/reasoning/engine.py` — Weighted evidence scoring engine. Takes all 7 signals,
  scores them by importance × reliability × status_factor, produces verdict + certainty score.
- `backend/app/detectors/` — All 7 detector modules (described below)
- `backend/app/models/` — Pydantic models for evidence, signals, reports
- `backend/app/chat/` — Session store (in-memory)
- `backend/app/reports/` — PDF forensic report builder (ReportLab)

### The 7 Detectors (keep all, do not remove any)
1. **spectral.py** — Custom-trained Six-Lens PyTorch model (ConvNeXt + FFT + SRM + Chroma + SPAI +
   Robustness). 249MB weights in `argusai_fuse_best/`. Has an autonomous self-test: if the model's
   predictions collapse (gap < 0.15 between real/AI classes), it **disables itself** to protect
   verdict integrity. This is the most important feature for the Arize story.
2. **metadata.py** — EXIF analysis. Detects AI tool fingerprints (Midjourney, DALL-E, etc.) directly
   in file metadata. High reliability (0.95) when it fires.
3. **noise.py** — Sensor noise pattern analysis. Real cameras have consistent thermal noise profiles.
   AI generators produce different noise statistics.
4. **lighting.py** — Lighting physics consistency. Checks brightness distribution against physical
   lighting behavior.
5. **semantic.py** — Gemini Vision. Checks for AI-specific visual anomalies: malformed fingers,
   impossible geometry, garbled text, missing shadows, AI watermarks. Most human-readable signal.
6. **ela.py** — Error Level Analysis. Re-saves image at lower quality, compares compression residuals.
   Produces a heatmap (base64 PNG) shown in the UI. Edited/composited regions show different stress.
7. **osint.py** — Live web fact-checking. Currently: generates search queries via Gemini, runs
   DuckDuckGo or Gemini grounded search, synthesizes findings. **NEEDS MAJOR UPGRADE** (see below).

### Frontend (React + Vite)
- `frontend/src/App.jsx` — Single-file React app, 1039 lines. Framer Motion animations,
  per-signal cards with animated confidence bars, ELA heatmap rendering, PDF download, session
  chat for follow-up questions. Already visually polished.
- `frontend/src/styles.css` — 39KB of custom CSS. Dark theme, glassmorphism, premium aesthetic.

### Model Weights
- `argusai_fuse_best/argusai_best_weights.pth` — 249MB PyTorch state dict
- **CRITICAL**: `.gitignore` currently excludes `*.pth`. This must be fixed with Git LFS before
  any deployment or submission. Anyone cloning the repo cannot run the spectral detector without
  the weights.

### What Does NOT Exist Yet
- Dockerfile
- Cloud Run deployment
- Google Cloud Agent Builder wrapper
- Arize Phoenix integration
- Reverse image search in OSINT
- Multi-hop OSINT research agent
- MIT License file in repo root
- Live hosted URL

---

## Strategic Decisions (Final, Do Not Revisit)

### Decision 1: OSINT Research Agent is the Headline Feature
The OSINT module is being upgraded from a one-shot search to a genuine multi-hop research agent.
This is the primary differentiator. No other deepfake detection tool does this.

**What it becomes:**
- User uploads image + optional context ("is this the Netanyahu ceasefire photo?")
- Agent performs reverse image search to find earliest known web appearance of this exact image
- Agent runs multi-hop Gemini function-calling loop: first search finds a lead → second search
  follows that lead → third search confirms or denies → synthesis across all hops
- Output: specific named sources ("Reuters published a fact-check on April 3rd"), dates, URLs,
  timeline contradictions ("image first appeared 3 weeks after the event it claims to show")
- This is investigation, not detection

**Reverse image search implementation**: TinEye API (free developer tier) or SerpAPI Google
Reverse Image Search (~$0.001/query). SerpAPI is preferred because it returns more structured data.

### Decision 2: Arize Phoenix — Circuit-Breaker Story (Not Calibration)
The Arize integration tells one specific story: **the system knows when it's broken.**

The spectral detector already has an autonomous self-disable mechanism. When it fails its
reference self-test, it removes itself from the verdict to prevent false positives. This happens
silently today. With Phoenix:
- Every analysis creates a Phoenix trace with 7 child spans (one per detector)
- Each span carries: detector ID, signal status, confidence, reliability, latency, verdict contribution
- When the spectral model disables itself, Phoenix logs a span with `circuit_breaker=True`
  and `reason="reference_self_test_failed"`
- A Phoenix dashboard shows: which detectors fired, which failed, historical patterns

**Why this beats the calibration story**: Calibration requires pre-running 50-100 images to have
meaningful historical data. The circuit-breaker story can be demonstrated live in the demo by
swapping in a degraded checkpoint. It's immediate, dramatic, and self-explanatory.

**The pitch**: "When the AI doesn't know it's broken, it keeps influencing decisions it should
have no part in. ArgusAI detects its own failures and removes broken components from the verdict.
Arize is the audit trail that proves it happened and tracks when it's happening."

**Removing Arize makes this audit trail invisible. That's what load-bearing means.**

### Decision 3: Keep All 7 Signals, Add Nothing New
Do not add more detector types. Seven is already impressive. Adding an 8th dilutes the story
without adding evidence quality. Each of the 7 already serves a distinct purpose and category.
The ELA heatmap is visually impressive in demos. The metadata detector catching Midjourney
fingerprints is a "wow moment" when it fires. Keep everything.

### Decision 4: The Demo Image is the Pope in the Puffer Coat
The 2023 viral Midjourney image of Pope Francis in a white puffer jacket is the perfect demo image:
- Metadata detector will fire (Midjourney fingerprint may be present)
- Spectral model should flag it
- Snopes has a specific article
- Reuters has a specific article  
- AP has coverage
- It is globally recognizable — every judge will know it
- The OSINT research agent will find the fact-checking coverage cleanly
- It's not politically contentious or offensive

Alternative demo images (backup):
- Fake Pentagon explosion image (May 2023)
- Trump arrest fake photos (March 2023)

### Decision 5: Framing is "Forensic Investigation Platform" Not "Deepfake Detector"
This distinction must appear in the README, demo narration, submission description, and UI copy.
"Deepfake detector" is a student project. "Forensic investigation platform" is a professional tool
that journalists, fact-checkers, and content moderation teams would actually use.

---

## What Needs to Be Built (Priority Order)

### Priority 1: MIT License File
**File**: `LICENSE` in repo root  
**Why first**: Automated Stage One screening checks for this. It takes 5 minutes. Failing it
disqualifies you before a human reads your submission.  
**Content**: Standard MIT License text with your name.

### Priority 2: Arize Phoenix Instrumentation
**Files to modify**: `backend/app/core/pipeline.py`  
**What to do**:
- Install `arize-phoenix-otel` and `openinference-instrumentation`
- Wrap `pipeline.analyze()` as a root Phoenix trace
- Each detector call in `run_detector_tracked` becomes a child span
- Span attributes: `detector.id`, `detector.status`, `detector.confidence`, `detector.reliability`,
  `detector.latency_seconds`, `detector.signal_support`, `detector.verdict_influence_percent`
- When spectral self-test fails: additional span attributes `circuit_breaker=True`,
  `circuit_breaker.reason`, `circuit_breaker.gap_score`
- Parent span attributes: `image.sha256`, `verdict`, `certainty`, `total_detectors`,
  `failed_detectors`, `pipeline.latency_seconds`
- Send to Arize Phoenix cloud (`app.phoenix.arize.com`) via OTLP
- Phoenix API key stored in env var `PHOENIX_API_KEY`

### Priority 3: OSINT Research Agent Upgrade
**Files to modify**: `backend/app/detectors/osint.py`, `backend/app/core/llm_client.py`  
**What to build**:

**Step A — Reverse Image Search**:
- Add `_reverse_image_search(image_bytes)` method to LLMClient
- Use SerpAPI Google Reverse Image endpoint (env var `SERPAPI_KEY`)
- Returns: list of {url, title, date, source} — known appearances of this image
- Fallback: TinEye API if SerpAPI unavailable
- Extract earliest known appearance date — this is forensically significant

**Step B — Multi-hop Research Loop**:
- Replace single-shot search with Gemini function-calling loop
- Tools available to the agent: `web_search(query)`, `reverse_image_search()`
- Loop: initial search → extract most significant result → formulate follow-up query → search again
  → synthesize (max 3 hops to control latency)
- Agent prompt: "You are a forensic investigative journalist. Use search to determine the
  provenance and authenticity of this image. Find: when it first appeared, what context it was
  originally shared in, whether fact-checkers have flagged it, whether the claimed event is real."
- Output must include: named sources with URLs, dates, direct quotes from fact-checkers,
  timeline analysis (image first appeared before/after claimed event)

**Step C — Synthesis Output Format**:
- `earliest_web_appearance`: { date, url, source_name }
- `fact_check_sources`: list of { outlet, verdict, url, date }
- `timeline_contradiction`: boolean + explanation
- `context`: 4-6 sentences with specific named sources, no generic hedging
- `research_hops`: number of search rounds conducted (visible to user — shows agentic depth)

### Priority 4: Google Cloud Agent Builder Wrapper
**What it is**: Vertex AI Agent Builder that wraps the ArgusAI backend as a tool-using agent  
**Minimal implementation**:
- Create Vertex AI Agent in Google Cloud Console
- Define tool: `analyze_image` — calls `POST /agent/analyze` on Cloud Run backend
- Define tool: `ask_question` — calls `POST /sessions/{id}/messages`
- Add a simplified `/agent/analyze` endpoint to FastAPI that returns stripped-down JSON
  (verdict, certainty, top 3 signals, OSINT summary) — Agent Builder needs simpler schemas
- The full rich API (`/sessions/{id}/analyze`) remains for the frontend
- Agent Builder integration is compliance, not the centerpiece — don't demo it for more than
  20 seconds

**IMPORTANT**: Agent Builder has an undocumented ~30s timeout on tool calls. Full analysis with
OSINT grounding can take 15-25s. If it times out, either disable OSINT for agent calls or make
the agent endpoint return a quick acknowledgment and poll for results.

### Priority 5: Dockerfile + Cloud Run Deployment
**Key constraints**:
- Must use `--memory=2Gi` minimum (model + PyTorch runtime = ~700MB)
- Use `--min-instances=1` to prevent cold starts (first request after cold start takes 30-45s
  due to ConvNeXt backbone loading)
- `--min-instances=1` costs ~$0.50-1.00/day — budget ~$15-20 total through judging period
- PyTorch CPU only: `pip install torch --index-url https://download.pytorch.org/whl/cpu`
- Model weights: store in Google Cloud Storage bucket, download at container startup
  (not in Docker image — 249MB adds to build time and image size)
- Set `SPECTRAL_REFERENCE_REAL_DIR=""` and `SPECTRAL_REFERENCE_AI_DIR=""` in Cloud Run env vars
  to skip self-test (no reference images in container) — detector degrades gracefully

**Dockerfile structure**:
```
FROM python:3.12-slim
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN python -c "import gcloud; download_weights()"  # or use startup script
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

### Priority 6: Git LFS for Model Weights
**Problem**: `.gitignore` currently excludes `*.pth`. Anyone cloning the repo gets a broken
spectral detector.  
**Fix**:
```bash
git lfs install
git lfs track "*.pth"
git add .gitattributes
git add argusai_fuse_best/argusai_best_weights.pth
git commit -m "Add model weights via Git LFS"
```
GitHub free tier includes 1GB LFS storage. 249MB fits.

---

## UX Decisions

### What Stays Exactly As Is
- The animated signal cards with per-detector confidence bars
- The ELA heatmap rendering (visually impressive, self-explanatory)
- The scanning animation during analysis
- The session chat for follow-up questions
- The PDF forensic report download
- The dark theme + glassmorphism aesthetic
- The landing page copy and layout

### What Gets Updated

**OSINT Signal Card** — Needs to show the new research agent outputs:
- "Research hops conducted: 3" (shows agentic depth)
- "Earliest web appearance: [date] on [source]" with a clickable link
- "Fact-checkers: [Snopes] [Reuters] [AP]" as named badges with links
- Timeline contradiction warning if image appeared after claimed event
- The current OSINT card layout is already wide (full-width) — extend it to show these fields

**New: Arize Health Badge** in the header/nav:
- Small badge showing "Monitored by Arize Phoenix" with a link to the live Phoenix dashboard
- When the circuit-breaker has fired on any detector in the last 24h: badge turns amber
  with "Detector anomaly detected — view in Arize"
- Implemented via a lightweight `/arize/health` endpoint that proxies Phoenix API
- This makes Arize visible to the user, not just to the developer — that's rare and impressive

**Verdict card** — Add one line: "Model health: All systems operational" or "Spectral detector
offline — verdict based on 6 signals" (already happens in the reasoning engine, just surface it)

### What Does NOT Need to Change
- The frontend is already polished enough to win. Do not spend time on UI overhaul.
- The PDF report is already impressive. Do not rebuild it.
- The chat interface works fine. Do not redesign it.

---

## Architecture Overview

```
User Browser
    │
    ▼
React Frontend (Vite)
    │  POST /sessions/{id}/analyze
    │  POST /sessions/{id}/messages
    ▼
FastAPI Backend (Cloud Run)
    │
    ├── AnalysisPipeline
    │   ├── [parallel] SpectralArtifactDetector  ─── Phoenix Span
    │   ├── [parallel] MetadataDetector           ─── Phoenix Span
    │   ├── [parallel] NoisePatternDetector       ─── Phoenix Span
    │   ├── [parallel] LightingConsistencyDetector─── Phoenix Span
    │   ├── [parallel] SemanticInconsistencyDetector── Phoenix Span (Gemini Vision)
    │   ├── [parallel] ErrorLevelAnalysisDetector ─── Phoenix Span
    │   └── [parallel] OSINTDetector              ─── Phoenix Span
    │       ├── Reverse Image Search (SerpAPI)
    │       └── Multi-hop Research Agent (Gemini function calling)
    │
    ├── ReasoningEngine → weighted verdict
    ├── LLMClient → narrative explanation (Gemini)
    └── Phoenix Root Trace (wraps entire pipeline)
    
Arize Phoenix Cloud
    └── Traces, spans, circuit-breaker events, dashboard

Google Cloud Agent Builder
    └── Wraps /agent/analyze and /agent/chat as tools
```

---

## Environment Variables

```bash
# Gemini (primary — handles vision, OSINT, narrative, search grounding)
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
GEMINI_VISION_MODEL=gemini-2.5-flash
GEMINI_GROUNDING_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.0-flash

# Model
SPECTRAL_MODEL_PATH=argusai_fuse_best
SPECTRAL_AI_INDEX=1
SPECTRAL_INPUT_SIZE=224
SPECTRAL_NORMALIZE=1
SPECTRAL_REFERENCE_REAL_DIR=Images Dataset/Real Images
SPECTRAL_REFERENCE_AI_DIR=Images Dataset/AI Images

# OSINT
OSINT_USE_GROUNDING=1
SERPAPI_KEY=                    # NEW — for reverse image search
TINEYE_API_KEY=                 # NEW — fallback reverse image search

# Arize Phoenix
PHOENIX_API_KEY=                # NEW — from app.phoenix.arize.com
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com  # or self-hosted

# App
MAX_UPLOAD_MB=20
LLM_EXPLANATION_PROVIDER=gemini
LLM_EXPLANATION_MAX_TOKENS=900
LLM_VISION_TIMEOUT_SECONDS=20
```

**NOTE**: Groq (`GROQ_API_KEY`, `groq_model`, etc.) must be removed from the codebase entirely.
The hackathon rules prohibit competing inference providers. Replace all Groq explanation paths
with Gemini equivalents. The `_gemini_text_explanation()` method already exists in `llm_client.py`.
This is a 2-hour refactor, not a blocker.

---

## The Demo Plan (3 Minutes)

**This is the most important document in this file. The demo is the submission.**

### Minute 1 — The Problem and the Investigation
- Open ArgusAI. Show the landing page briefly (establishes it's a polished product).
- Upload the Pope in Puffer Coat image.
- Add context: "Is this a real photo of Pope Francis?"
- Hit analyze. Show the scanning animation (establishes it's doing real work in parallel).
- While scanning: narrate "Seven forensic detectors are running simultaneously — spectral
  frequency analysis, physical sensor noise, lighting physics, and a live research agent
  searching the web right now for where this image came from."
- Results appear. Cut straight to the OSINT card.

### Minute 2 — The OSINT Research Agent (The Showstopper)
- Show the OSINT card expanded: "Research agent conducted 3 search hops."
- Show: "Earliest known web appearance: March 25, 2023 on Twitter"
- Show: "Fact-checkers: Reuters (March 27) • AP (March 26) • Snopes (March 26)"
- Show the specific finding: "All three outlets confirmed this image was generated by Midjourney.
  The Pope never wore this outfit."
- Brief cut to the Metadata card: "Metadata detector also found a generative software fingerprint
  directly in the file."
- Verdict card: "Likely AI Generated — 89% certainty."
- Narrate: "This isn't a score. This is evidence. You can see exactly what each check found and
  why it matters. Click any signal for the full reasoning."

### Minute 3 — Arize Phoenix (The Technical Proof)
- Cut to Arize Phoenix dashboard (have it open in another tab).
- Show the trace from the analysis just run: parent span + 7 child spans.
- Point out: detector latencies, which fired (OK), which had warnings.
- Show a previously captured trace where the spectral circuit-breaker fired:
  `circuit_breaker=True`, `reason=reference_self_test_failed`
- Narrate: "When the spectral model detected its own predictions were unreliable, it removed
  itself from the verdict. Arize is the audit trail that proves it happened — and tracks when
  it happens across all analyses over time."
- Show the Arize health badge in the ArgusAI header.
- End on: "ArgusAI doesn't just analyze images. It investigates them — and it knows when
  to distrust itself. That's what makes it a forensic platform, not a classifier."

### What to NOT Demo
- The PDF report (mention it exists, don't show it — it eats time)
- The chat follow-up (mention it exists)
- Agent Builder (a screenshot or 10 seconds max — it's compliance not a feature)
- The JSON export
- Multiple different images

---

## Key Technical Risks and Mitigations

**Risk: OSINT agent takes too long (>30s)**  
Mitigation: OSINT runs in parallel with other detectors already. Cap research hops at 3.
Add per-hop timeout of 8 seconds. If OSINT times out, degrade gracefully (already does this).

**Risk: timm model resolution fails in container**  
Mitigation: `timm==0.9.7` is pinned. Test the Docker build with a full analysis request before
recording the demo. `pretrained=False` means no weight download at runtime.

**Risk: Agent Builder tool call timeout (undocumented ~30s limit)**  
Mitigation: Add `/agent/analyze` endpoint that disables OSINT and returns simplified JSON.
The full frontend uses the rich endpoint. Agent Builder uses the stripped endpoint.

**Risk: Phoenix cloud trace retention**  
Mitigation: Keep Cloud Run instance running through judging period (--min-instances=1).
New traces will accumulate from judge testing. Also generate a reference trace set before
the demo by running 20+ known images through the pipeline.

**Risk: SerpAPI reverse image search returns no results**  
Mitigation: Handle gracefully — OSINT still runs text search. Reverse image search enriches
the output when it finds results, doesn't block when it doesn't.

---

## Dataset and License Notes

**Training datasets used for spectral model weights**:
- `ayushmandatta1/deepdetect-2025` (Kaggle) — verify license before publishing weights
- `Rajarshi-Roy/Defactify_Image_Dataset` (Hugging Face) — verify license before publishing weights

If either dataset restricts commercial use, the trained weights cannot be published under MIT.
In that case: either exclude the weights from the repo and document as "bring your own weights,"
or retrain on clearly permissive datasets. The spectral detector degrades gracefully when weights
are absent (returns UNAVAILABLE status, reasoning engine compensates).

**Code license**: MIT. Add `LICENSE` file to repo root immediately.

---

## File Structure (Relevant Parts)

```
ArgusAI/
├── CLAUDE.md                          ← This file
├── LICENSE                            ← MUST ADD (MIT)
├── README.md                          ← Update after implementation
├── .gitattributes                     ← MUST ADD (Git LFS tracking)
├── .env.example                       ← Update with new env vars
├── Dockerfile                         ← MUST BUILD
├── render.yaml                        ← Keep for reference, deploy to Cloud Run instead
├── training_model.py                  ← Training script, do not modify
├── argusai_fuse_best/
│   └── argusai_best_weights.pth       ← 249MB, must be in Git LFS
├── backend/
│   ├── requirements.txt               ← Add arize-phoenix-otel, openinference, serpapi
│   └── app/
│       ├── main.py                    ← Add /agent/* endpoints
│       ├── core/
│       │   ├── pipeline.py            ← ADD Phoenix instrumentation (primary Arize work)
│       │   ├── llm_client.py          ← ADD reverse image search, multi-hop agent, REMOVE Groq
│       │   ├── llm.py                 ← REMOVE Groq settings, ADD Phoenix/SerpAPI settings
│       │   └── config.py              ← ADD new env var mappings
│       ├── detectors/
│       │   └── osint.py               ← REPLACE with research agent implementation
│       └── ...                        ← Everything else stays as-is
└── frontend/
    └── src/
        ├── App.jsx                    ← ADD Arize health badge, UPDATE OSINT card layout
        └── styles.css                 ← Minor additions only
```

---

## Tone and Voice (For Copy, README, Demo)

- **Not**: "AI-powered deepfake detection tool"
- **Yes**: "Forensic investigation platform for image authenticity"

- **Not**: "Our model detects AI-generated images"  
- **Yes**: "Seven parallel forensic detectors build an evidence trail"

- **Not**: "Integrated with Arize for monitoring"  
- **Yes**: "Arize Phoenix is the audit trail for our autonomous detector health system"

- **Not**: "High accuracy deepfake detector"  
- **Yes**: "A system that knows when to distrust itself"

The product exists for: journalists verifying images before publication, fact-checkers
investigating viral claims, content moderation teams, anyone who needs to answer the question
"can I trust what I'm seeing?" with evidence rather than a number.

---

*Last updated: May 28, 2026. This document reflects all strategic decisions made through
the initial rebranding phase. All implementation decisions should be consistent with this
document. When in doubt: forensic platform, not classifier. Evidence trail, not score.*
