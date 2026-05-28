# CLAUDE.md — ArgusAI Hackathon Source of Truth

Last updated: May 28, 2026.

This file is the handoff document for fresh sessions. It captures what ArgusAI is, what has been implemented for the hackathon, and why the current path is the highest-leverage route for the Arize track.

## What ArgusAI Is

ArgusAI is a forensic investigation platform for image authenticity. It is not positioned as a generic deepfake detector or a single classifier.

The product answer is not “87% fake.” The product answer is an evidence trail:

- What the pixels suggest.
- What the file metadata suggests.
- What the lighting and noise physics suggest.
- What live public sources say about the image or claim.
- Whether any detector was unhealthy and removed from the verdict.

The core phrase to preserve everywhere:

> Forensic investigation platform, not classifier. Evidence trail, not score.

## Hackathon Context

Competition: Google Cloud Rapid Agent Hackathon, Arize partner track.

Submission needs:

- Gemini and Google Cloud Agent Builder.
- Meaningful Arize/Phoenix integration.
- Hosted web app.
- Public repo with visible open-source license.
- 3-minute demo video.

Judging categories are equal weight:

- Technological implementation.
- Design/UX.
- Potential impact.
- Quality/creativity of idea.

The product should be built and narrated for journalists, fact-checkers, content moderation teams, and anyone verifying viral images before trusting or publishing them.

## Strategic Decision

Commit to ArgusAI. The base is strong enough to win if the Arize integration is causal, not decorative.

The winning story is:

> ArgusAI investigates images like a forensic newsroom, and Arize Phoenix is the audit layer that lets the system know when one of its own detectors should not be trusted.

The old “add Arize traces” plan was not enough. The current implementation upgrades this into a reliability governor:

- Every analysis can emit a Phoenix root trace.
- Each detector runs as a child span.
- Circuit-breaker events are marked in span attributes.
- Detector health is stored locally in `logs/arize/detector_health.json`.
- If a detector trips a health gate, it is held out of future verdict influence during the TTL.

Removing Arize now removes the audit trail for autonomous detector health. That is the Arize track story.

## What Is Implemented Now

Backend:

- `backend/app/main.py`
  - FastAPI app.
  - Session analysis.
  - Follow-up chat.
  - PDF export.
  - `/health`.
  - `/arize/health`.
  - `/agent/analyze`.
  - `/agent/chat`.
- `backend/app/core/pipeline.py`
  - Runs seven detectors in parallel.
  - Emits x-ray logs to `logs/xray/`.
  - Wraps analysis in Phoenix/OpenTelemetry spans.
  - Records detector health events.
  - Adds `pipeline_health` to reports.
- `backend/app/core/observability.py`
  - Phoenix tracing setup.
  - Safe no-op behavior if Phoenix packages/env vars are missing.
- `backend/app/core/health_governor.py`
  - File-backed detector health gate.
  - Makes circuit-breakers affect future verdicts.
- `backend/app/core/llm_client.py`
  - Gemini-only LLM client.
  - Semantic vision.
  - Grounded OSINT research agent.
  - Optional SerpAPI Google Lens reverse-image enrichment when a public image URL is supplied in context.
  - Gemini narrative and follow-up answers.
- `backend/app/detectors/osint.py`
  - Upgraded from one-shot search to research-agent-shaped output.
  - Returns research hops, earliest appearance candidate, fact-check sources, timeline contradiction, search queries, and reverse-image matches.
- `backend/app/detectors/spectral.py`
  - Six-Lens model.
  - Reference self-test circuit breaker.
  - Circuit-breaker metadata now includes reason and gap score.

Frontend:

- `frontend/src/App.jsx`
  - Arize health badge in header.
  - Verdict card surfaces detector health.
  - OSINT card surfaces research hops, earliest appearance, fact-checkers, and timeline contradictions.
- `frontend/src/styles.css`
  - Styling for Arize badge and OSINT research panel.
- `mcp/phoenix-mcp.json`
  - Template config for the official `@arizeai/phoenix-mcp` server.
- `ContextFiles/AgentBuilderPhoenixSetup.md`
  - Setup notes for Agent Builder tools and Phoenix MCP.

Docs/config:

- `README.md` rewritten around current hackathon state.
- `.env.example` added.
- `backend/requirements.txt` includes Phoenix/OpenInference packages.
- `LICENSE`, `.gitattributes`, and `Dockerfile` exist.

## The Seven Detectors

Keep all seven. Do not add an eighth detector unless a future user explicitly asks and there is a compelling reason.

1. Spectral artifacts: custom Six-Lens PyTorch model.
2. Metadata and provenance: EXIF and AI generator fingerprints.
3. Noise pattern analysis: sensor noise and smooth dead-zone checks.
4. Lighting consistency: exposure and contrast physics.
5. Semantic consistency: Gemini vision checks for visible AI anomalies.
6. Error Level Analysis: compression residual heatmap.
7. OSINT verification: Gemini grounded research agent plus optional reverse-image enrichment.

## Current Arize Story

Use Phoenix for two layers:

1. Tracing
   - Root span: `argusai.analysis`.
   - Detector spans: `detector.<id>`.
   - Attributes include detector status, reliability, confidence, latency, support, circuit-breaker state, and parent verdict/certainty.

2. Reliability governor
   - Circuit-breaker events are persisted.
   - Active anomalies show in `/arize/health`.
   - The frontend badge turns into “Detector anomaly detected - view in Arize.”
   - A disabled detector returns an unavailable signal and contributes zero verdict weight.

This is the most important technical differentiator.

## Current OSINT Story

The OSINT module should be demoed as the user-facing showstopper.

For the Pope puffer image, the card should show:

- Research hops conducted.
- Earliest web appearance candidate if found.
- Fact-checkers as named source badges.
- Timeline contradiction if present.
- Plain-language synthesis naming sources and dates.

Important honesty constraint:

Reverse image search requires a public image URL for SerpAPI Google Lens. For normal uploads, ArgusAI uses Gemini grounded research from the image and user claim. Do not claim exact reverse search worked unless the response actually includes matches.

## Demo Plan

One image only: Pope Francis white puffer jacket.

Narrative:

1. “This is not a classifier. It is a forensic investigation.”
2. Upload image and context.
3. Show seven detectors running.
4. Show OSINT research card with named sources.
5. Show verdict and evidence influence.
6. Cut to Phoenix trace.
7. Show prepared spectral circuit-breaker trace.
8. Explain that ArgusAI removed an unhealthy detector from the verdict.

Do not spend demo time on:

- PDF report.
- Raw JSON.
- Multiple images.
- Long Agent Builder walkthrough.

Agent Builder only needs a short compliance shot showing it can call `/agent/analyze` and `/agent/chat`.

## Known Gaps / Next Work

- Deploy to Cloud Run and verify memory/cold-start behavior.
- Configure Phoenix Cloud env vars.
- Configure Agent Builder tools.
- Connect Phoenix MCP with `mcp/phoenix-mcp.json`.
- Test with real Pope image and capture a successful trace.
- Decide model weight distribution based on dataset licenses.
- If the model weights cannot be published, document “bring your own weights” or host them outside the repo for the demo.
- The local environment used by this Codex session did not have the PyTorch spectral runtime, so the app imports and a synthetic analysis run succeeded, but the spectral detector degraded to `error`. Re-test with full backend dependencies before the demo.

## Environment Variables

See `.env.example`.

Core:

- `GEMINI_API_KEY`
- `PHOENIX_API_KEY`
- `PHOENIX_COLLECTOR_ENDPOINT`
- `PHOENIX_DASHBOARD_URL`
- `SERPAPI_KEY`
- `SPECTRAL_MODEL_PATH`
- `ARIZE_HEALTH_GOVERNOR=1`

No competing inference providers are used in code after the current update.

## Engineering Rule

When making future changes, preserve the winning shape:

- Do not dilute the demo with feature variety.
- Do not overhaul the UI.
- Do not add more detectors.
- Make Arize more causal if you touch Arize at all.
- Make OSINT more source-specific if you touch OSINT at all.
