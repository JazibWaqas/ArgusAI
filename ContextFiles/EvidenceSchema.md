# ArgusAI Evidence Schema

**✅ IMPLEMENTED** - This schema is fully implemented in `backend/app/models/evidence.py` using Pydantic models.

This schema defines the structured evidence produced by detectors and consumed by the reasoning layer.

## EvidenceSignal

**Implementation:** `backend/app/models/evidence.py`

```python
class EvidenceSignal(BaseModel):
    id: str = Field(..., description="Stable identifier for the signal.")
    name: str
    category: str
    status: SignalStatus
    reliability: float = Field(..., ge=0.0, le=1.0)
    summary: str
    what_checked: Optional[str] = None
    what_found: Optional[str] = None
    why_it_matters: Optional[str] = None
    caveat: Optional[str] = None
    observations: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    supports: SignalSupport = SignalSupport.UNKNOWN
    notes: Optional[str] = None
    verdict_influence_percent: Optional[int] = None  # 0–100, set by pipeline after reasoning
```

**Field Descriptions:**
- `id`: Stable identifier for the detector (string).
- `name`: Human-readable signal name (string).
- `category`: Signal category (string).
- `status`: One of `ok`, `warning`, `unavailable`, `error` (SignalStatus enum).
- `reliability`: Estimated reliability between `0.0` and `1.0` (validated).
- `summary`: Short summary of what the signal observed.
- `what_checked`: Description of the forensic methodology used.
- `what_found`: Specific finding in the current image.
- `why_it_matters`: Reasoning for how this finding impacts authenticity.
- `caveat`: Potential limitations or common false positives for this signal.
- `observations`: List of specific technical observations (strings).
- `metrics`: Structured numeric or categorical measurements (object).
- `confidence`: Optional detector confidence between `0.0` and `1.0` (validated).
- `supports`: One of `authentic`, `ai_generated`, `inconclusive`, `unknown` (SignalSupport enum).
- `notes`: Optional contextual notes or caveats.

## EvidenceProfile

**Implementation:** `backend/app/models/evidence.py`

```python
class EvidenceProfile(BaseModel):
    image: ImageInfo
    signals: List[EvidenceSignal]
    warnings: List[str] = Field(default_factory=list)
```

- `image`: Image metadata (ImageInfo object).
- `signals`: List of `EvidenceSignal` objects.
- `warnings`: System-level warnings (list of strings).

## ImageInfo

**Implementation:** `backend/app/models/evidence.py`

```python
class ImageInfo(BaseModel):
    width: int
    height: int
    mode: str
    sha256: str
    format: Optional[str] = None
```

- `width`: Image width in pixels.
- `height`: Image height in pixels.
- `mode`: Image color mode (e.g., "RGB").
- `sha256`: SHA-256 hash of the image bytes.
- `format`: Optional image format (e.g., "JPEG", "PNG").

## Enums

**SignalStatus Enum:**
- `OK = "ok"`
- `WARNING = "warning"`
- `UNAVAILABLE = "unavailable"`
- `ERROR = "error"`

**SignalSupport Enum:**
- `AUTHENTIC = "authentic"`
- `AI_GENERATED = "ai_generated"`
- `INCONCLUSIVE = "inconclusive"`
- `UNKNOWN = "unknown"`

## Example EvidenceSignal

```json
{
  "id": "metadata_analysis",
  "name": "Metadata & Provenance",
  "category": "metadata",
  "status": "ok",
  "reliability": 0.35,
  "summary": "Metadata review completed.",
  "observations": [
    "Camera make: Canon",
    "Camera model: EOS R5"
  ],
  "metrics": {
    "exif_count": 24
  },
  "confidence": null,
  "supports": "authentic",
  "notes": "Missing metadata alone does not imply AI generation."
}
```

## Current Usage

All 7 detectors return `EvidenceSignal` objects that are aggregated into an `EvidenceProfile` by the analysis pipeline. The reasoning engine then processes this structured evidence to generate verdicts and explanations.
