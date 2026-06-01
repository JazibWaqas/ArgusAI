# ArgusAI Vision

Last updated: June 2, 2026.

Read `ContextFiles/CurrentHandoff.md` first for live URLs, deployed revisions, secrets, and exact next actions. This file explains the product logic and why the architecture was shaped this way.

## One-Line Product Definition

ArgusAI is a multi-modal forensic investigation platform for image, video, and audio authenticity.

It is not a classifier. It is an evidence trail.

Core phrase to preserve in copy, demo narration, Agent Builder prompts, and Devpost:

> Forensic investigation platform, not classifier. Evidence trail, not score.

## Who It Is For

ArgusAI is designed for people who need to verify media before acting on it:

- journalists and newsroom researchers
- courts and legal teams
- fact-checkers
- content moderation and trust/safety teams
- public-interest investigators

The product should feel like professional forensic tooling. Avoid toy classifier language like "AI score" or "fake percentage" as the main framing.

## The Problem

Generative media is now good enough that humans can be fooled by images, videos, and cloned voices. At the same time, real media can be falsely accused of being AI-generated.

Both errors matter:

- false trust can spread misinformation or fabricated evidence
- false accusation can damage real documentation

ArgusAI reduces those risks by showing multiple independent forms of evidence, where they agree, where they conflict, and how much trust each signal deserves.

## What Makes ArgusAI Different

Most AI detectors present one confidence number. ArgusAI separates the work into five layers:

1. Evidence extraction: detectors inspect pixels, metadata, audio, temporal consistency, and public provenance.
2. Evidence reasoning: only applicable and healthy signals influence the verdict.
3. Persistent intelligence: Firestore accumulates analysis history, detector reliability, feedback, and health state.
4. Auditability: Phoenix records the trace of each verdict so a user can inspect what happened and when.
5. Self-calibration: human-confirmed outcomes feed back into how much each detector is trusted (see below). This is the launch-worthy differentiator.

The demo story:

> Every verdict is backed by two layers. Firestore tells you how reliable each signal has been across past investigations. Phoenix gives you the immutable audit trail for this specific decision.

## Self-Calibration: The Closed Loop (added June 2, 2026)

This is the core "why this wins" idea, clarified directly by the project owner: ArgusAI should be a genuinely reliable system that *measurably improves itself* from real use — not a static classifier. The data we capture is the right level to adjust signal weightings and, over time, improve the signals themselves.

The loop, implemented and causal:

1. Every analysis → Phoenix trace (audit) + Firestore record (data).
2. The user confirms the verdict (Yes/No widget on the report) → human ground truth.
3. Per-detector **confirmed accuracy** is tracked in Firestore (`detector_stats.confirmed_total / confirmed_correct / confirmed_accuracy`). This is distinct from the older `accuracy_rate`, which is *self-agreement* (how often a detector sided with the system's own verdict) and is therefore circular — confirmed accuracy vs. human truth is the number that actually means something.
4. `get_learned_weights()` converts confirmed accuracy into a per-detector weight multiplier, gated (needs `LEARNED_WEIGHT_MIN_CONFIRMATIONS`, env-tunable, default 8), bounded 0.5x–1.5x, with 0.6 confirmed accuracy mapping to 1.0x (no change).
5. The verdict engine (`backend/app/reasoning/engine.py` `_score_signal`) multiplies each detector's `base_weight` by that learned multiplier. So observability is **causal to the output** — the exact Arize partner-track thesis, made real rather than decorative.

Why gated/bounded: the demo must stay stable. Until a detector earns enough confirmations its multiplier is exactly 1.0, so behaviour does not drift; then it visibly adapts. The Arize Reliability Console surfaces this as a "Self-calibration active" banner plus per-detector applied-weight pills (↑1.30× / ↓0.50×).

Framing the owner emphasized: judges will not deeply audit which layer is Firestore vs Phoenix. What matters is that the Arize/observability story is genuinely meaningful and useful, and that the self-improvement is real — not theatre. Build for "launch-worthy product," not just "demo."

## Arize/Phoenix Strategy

The Arize partner-track integration is meant to be load-bearing, not decorative.

Phoenix does three important jobs:

- records root analysis traces and detector child spans
- exposes circuit-breaker and calibration behavior when detectors become unreliable
- provides the chain-of-custody audit trail linked from the verdict card, signal details, admin panel, and PDF

The health governor uses detector behavior to affect verdict influence. If a detector is unhealthy or repeatedly divergent, it can be attenuated or held out. That is the winning angle: observability changes the product outcome.

## Firestore Strategy

Firestore is the persistent intelligence layer.

It stores:

- `/analyses/{sha256}` records with verdict, media type, detector outputs, feedback, and `phoenix_trace_id`
- global analysis counts by media type and verdict (`stats/global`)
- `stats/feedback`: global human-confirmed accuracy counters (`confirmed_correct`, `confirmed_incorrect`, `total_feedback`) — powers the console's "real-world accuracy" hero stat
- `detector_stats/{id}`: reliability stats and average latency, plus the confirmed-accuracy counters that drive self-calibration
- health governor state

This matters because Cloud Run container filesystems are ephemeral. Local `logs/xray/*.json` still exist as fallback, but Firestore is what makes history survive restarts and deployments.

Local Firebase connects via Application Default Credentials (or `GOOGLE_APPLICATION_CREDENTIALS` / `firebase-key.json`). Known gotcha: `get_db()` must not permanently cache a failed init — a transient cold-start failure used to disable Firebase for the whole process (feedback returned 503, `/stats` silently fell back to `source: xray`). It now caches only a successful client and retries.

## Agent Builder Strategy

The Agent Builder endpoints are not generic Gemini wrappers anymore.

- `/agent/analyze` runs ArgusAI and returns a compact tool-friendly report.
- `/agent/chat` answers follow-up questions about the prior report.
- Both now include Firestore history context, detector reliability stats, same-media analysis counts, recent same-media cases, and Phoenix trace IDs.

This lets the agent say things like:

> We have persisted 47 prior investigations. For this media type, spectral artifacts has matched final verdict direction in 87% of eligible runs.

That is the requirement-meeting story: Gemini plus Agent Builder acts on a real forensic system with memory and partner observability.

## Current Media Scope

ArgusAI now supports:

- image: full seven-signal investigation
- video: frame extraction, semantic video review, temporal coherence, OSINT, frame-based spectral/ELA, optional embedded audio track
- audio: voice authenticity signal, Gemini semantic listening, OSINT context

The UI and backend must stay media-aware. Do not show image-only noise/lighting signals for audio. Do not describe audio/video as photographs. Use `media_type` and each signal's `visible` field.

## Ethical Design

ArgusAI must be honest about uncertainty.

When evidence conflicts or is weak, the right answer is:

> Inconclusive.

Do not overclaim. Do not imply legal certainty. The product is a structured aid to human judgment, not a replacement for it.

## Demo North Star

For the final hackathon recording, show:

1. Upload a strong synthetic or famous debunked media sample.
2. Show the evidence trail, not just the verdict.
3. Open OSINT/provenance details.
4. Show the verdict card's Phoenix audit link.
5. Open the admin panel and explain: "Firestore persists investigation history; Phoenix records the immutable trace for every verdict."
6. Show Agent Builder using `/agent/analyze` and `/agent/chat`.

Skip new detector work unless a bug blocks the demo. The system is strong enough; the remaining challenge is configuration, narrative, and clean recording.
