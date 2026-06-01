# ArgusAI Evidence Schema

Last updated: June 2, 2026.

This file summarizes the current report/evidence shapes for a fresh engineering session. The source of truth is the Pydantic code in `backend/app/models/`.

## Core Report Types

### ForensicReport

Implementation: `backend/app/models/report.py`

Used for image and video reports.

Important fields:

```python
class ForensicReport(BaseModel):
    media_type: str
    verdict: Verdict
    certainty: float
    confidence_label: str
    leaning: Optional[Verdict]
    short_summary: str
    explanation: str
    score_breakdown: ScoreBreakdown
    evidence: EvidenceProfile
    pipeline_health: dict[str, Any]
    phoenix_trace_id: Optional[str]
    generated_at: datetime
```

Key additions:

- `media_type` is `image`, `video`, or `audio` depending on route/report shape.
- `phoenix_trace_id` links the report to Phoenix audit trail.
- `pipeline_health` carries model/governor state.

### AudioForensicReport

Implementation: `backend/app/models/audio_report.py`

Used for standalone audio reports.

Important fields include:

- `media_type`
- `verdict`
- `certainty`
- `confidence_label`
- `short_summary` / `explanation`
- primary audio `signal`
- optional `phoenix_trace_id`
- `pipeline_health`
- `generated_at`

The frontend has a separate `AudioReportCard` because this schema is intentionally smaller than the image/video evidence profile.

## EvidenceSignal

Implementation: `backend/app/models/evidence.py`

```python
class EvidenceSignal(BaseModel):
    id: str
    name: str
    category: str
    status: SignalStatus
    reliability: float
    summary: str
    what_checked: Optional[str]
    what_found: Optional[str]
    why_it_matters: Optional[str]
    caveat: Optional[str]
    observations: List[str]
    metrics: Dict[str, Any]
    confidence: Optional[float]
    supports: SignalSupport
    notes: Optional[str]
    verdict_influence_percent: Optional[int]
    visible: bool
```

Important behavior:

- `visible=false` means the frontend should hide the card.
- Hidden signals should not influence reasoning.
- `verdict_influence_percent` is assigned after reasoning.
- `metrics` may contain heavy fields like `ela_image_base64`; these are stripped before PDF payload rendering.

## EvidenceProfile

Implementation: `backend/app/models/evidence.py`

```python
class EvidenceProfile(BaseModel):
    image: ImageInfo
    signals: List[EvidenceSignal]
    warnings: List[str]
```

For video, `image` refers to representative/extracted-frame metadata rather than a literal uploaded still image. Keep UI language media-aware.

## ImageInfo

Implementation: `backend/app/models/evidence.py`

```python
class ImageInfo(BaseModel):
    width: int
    height: int
    mode: str
    sha256: str
    format: Optional[str]
```

`sha256` is important because Firestore stores analyses under `/analyses/{sha256}`.

## Enums

Signal statuses:

- `ok`
- `warning`
- `unavailable`
- `error`

Signal support:

- `authentic`
- `ai_generated`
- `inconclusive`
- `unknown`

Verdicts:

- `likely_authentic`
- `likely_ai_generated`
- `inconclusive`

Audio may expose equivalent audio-specific labels in frontend copy while keeping backend values structured.

## Firestore Analysis Record

Implementation: `backend/app/core/analysis_store.py`

Stored under:

```text
/analyses/{sha256}
```

Shape:

```json
{
  "timestamp": "ISO string",
  "sha256": "content hash",
  "media_type": "image | video | audio",
  "verdict": "likely_ai_generated | likely_authentic | inconclusive",
  "certainty": 0.795,
  "phoenix_trace_id": "trace id or null",
  "detectors": {
    "spectral_artifacts": {
      "support": "ai_generated",
      "confidence": 0.61,
      "latency_seconds": 1.23,
      "status": "ok",
      "visible": true,
      "circuit_breaker": false
    }
  },
  "latency_seconds": 12.34,
  "user_feedback": null,
  "feedback_timestamp": null
}
```

## Stats Shape

Endpoint:

```text
GET /stats
```

Returns Firestore-backed stats when available:

```json
{
  "global": {
    "total_analyses": 52,
    "by_media_type": {
      "image": 34,
      "video": 12,
      "audio": 6
    },
    "by_verdict": {
      "likely_ai_generated": 31,
      "likely_authentic": 14,
      "inconclusive": 7
    }
  },
  "detectors": {
    "spectral_artifacts": {
      "total_runs": 46,
      "correct_count": 40,
      "accuracy_rate": 0.87,
      "avg_latency_seconds": 8.2
    }
  },
  "source": "firestore"
}
```

If Firebase is unavailable, `/stats` falls back to local x-ray logs.

## Agent Builder History Context

Implementation: `build_history_context()` in `backend/app/core/analysis_store.py`.

Injected into `/agent/analyze` responses and `/agent/chat` evidence payloads.

Includes:

- `source`
- `summary`
- `total_analyses`
- `same_media_type_analyses`
- `by_media_type`
- `by_verdict`
- `detector_reliability`
- `recent_same_media_cases`

This is how the Agent Builder layer can talk about accumulated system reliability instead of only the current upload.

## PDF / Chain of Custody

Official PDFs now include:

- report generation timestamp
- reference/session ID when available
- forensic trace ID
- Phoenix audit URL when available
- footer: `ArgusAI chain of custody | Trace: ... | Generated: ...`

This supports the journalist/court demo narrative.
