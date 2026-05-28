# ArgusAI Architecture

Last updated: May 28, 2026.

ArgusAI is a multi-signal forensic investigation platform. The architecture is organized around evidence extraction, detector health governance, evidence reasoning, and user-facing provenance explanation.

## High-Level Flow

Image upload  
→ FastAPI session or Agent Builder endpoint  
→ PIL preprocessing and SHA-256 hashing  
→ Seven detector tasks run in parallel  
→ Phoenix root trace and detector child spans  
→ Arize reliability governor records circuit-breaker events  
→ Reasoning engine combines only usable evidence  
→ Gemini writes the plain-language explanation  
→ React UI shows verdict, signal cards, OSINT research trail, and Arize health

## Core Files

- `backend/app/main.py` - FastAPI app, session endpoints, Agent Builder endpoints, health endpoints.
- `backend/app/core/pipeline.py` - Analysis orchestration, parallel detector execution, Phoenix spans, x-ray logs, report assembly.
- `backend/app/core/observability.py` - Phoenix/OpenTelemetry setup with safe no-op fallback.
- `backend/app/core/health_governor.py` - Detector health gate backed by `logs/arize/detector_health.json`.
- `backend/app/reasoning/engine.py` - Weighted evidence synthesis.
- `backend/app/core/llm_client.py` - Gemini vision, OSINT research, narrative, and chat.
- `frontend/src/App.jsx` - Upload flow, forensic report UI, Arize badge, OSINT research display.

## Detectors

1. `spectral.py` - Six-Lens PyTorch fusion model.
2. `metadata.py` - EXIF and generative software traces.
3. `noise.py` - sensor noise and smooth dead-zone analysis.
4. `lighting.py` - exposure and lighting physics.
5. `semantic.py` - Gemini vision for visible physical anomalies.
6. `ela.py` - JPEG error level analysis and heatmap.
7. `osint.py` - Gemini grounded provenance research and optional public-URL reverse-image enrichment.

## Arize Reliability Layer

Phoenix tracing is not decorative. The pipeline creates:

- root span: `argusai.analysis`
- detector spans: `detector.<detector_id>`

Detector spans include:

- `detector.id`
- `detector.status`
- `detector.confidence`
- `detector.reliability`
- `detector.latency_seconds`
- `detector.signal_support`
- `detector.circuit_breaker`
- `detector.circuit_breaker.reason`
- `detector.circuit_breaker.gap_score`

The root span includes:

- `image.sha256`
- `verdict`
- `certainty`
- `total_detectors`
- `failed_detectors`
- `pipeline.latency_seconds`
- `detector.<id>.verdict_influence_percent`

When the spectral self-test fails, the detector emits a circuit-breaker signal. The health governor records it and future analyses hold that detector out of the verdict during the TTL.

## OSINT Research Layer

The OSINT detector now returns structured provenance fields:

- `research_hops`
- `earliest_web_appearance`
- `fact_check_sources`
- `timeline_contradiction`
- `search_queries`
- `reverse_image_matches`

Reverse-image enrichment is only attempted when the user context includes a public image URL and `SERPAPI_KEY` is configured. Otherwise Gemini grounded research handles the public-source investigation.

## Report Shape

`ForensicReport` now includes:

- `verdict`
- `certainty`
- `confidence_label`
- `short_summary`
- `explanation`
- `score_breakdown`
- `evidence`
- `pipeline_health`
- `generated_at`

`EvidenceProfile` now includes `health`, so detector health is part of the evidence bundle.

## Agent Builder Surface

The full frontend uses `/sessions/{id}/analyze`.

Google Cloud Agent Builder should call:

- `POST /agent/analyze`
- `POST /agent/chat`

These return smaller schemas designed for tool use rather than the full rich frontend payload.
