# ArgusAI System Architecture

This document describes the conceptual architecture and **current implementation** of ArgusAI.

---

## Current Implementation Status

**✅ Fully Implemented Architecture**

The system described in this document has been built and is operational:

- **FastAPI Backend** (`backend/app/main.py`) - Async REST API with CORS
- **React Frontend** (`frontend/src/App.jsx`) - Modern UI with Vite
- **7 Production Detectors** in `backend/app/detectors/`
- **Async Pipeline** (`backend/app/core/pipeline.py`) with parallel processing
- **LLM Reasoning Engine** (`backend/app/reasoning/engine.py`)
- **Evidence Models** (`backend/app/models/`) with Pydantic validation
- **Performance Logging** (`logs/xray/`) for monitoring
- **Environment Configuration** with API key management

---

# System Overview

ArgusAI is built as a **multi-signal forensic analysis pipeline**.

The system analyzes an input image using multiple independent detectors, aggregates the resulting evidence, and generates a human-readable forensic report.

The architecture separates three key responsibilities:

1. Evidence extraction
2. Evidence aggregation  
3. Reasoning and explanation

---

# Core Pipeline

**Implemented in:** `backend/app/core/pipeline.py`

The high-level pipeline is:

Image Input (FastAPI UploadFile)  
→ Image Preprocessing (PIL RGB conversion)  
→ **Parallel Evidence Extraction** (asyncio.gather)  
→ Evidence Aggregation (EvidenceProfile)  
→ **LLM Reasoning Engine** (Gemini/Groq)  
→ Forensic Report (Pydantic model)  
→ Frontend Visualization (React components)

**Current Implementation Details:**
- All 7 detectors run concurrently using `asyncio.gather()`
- Each detector is wrapped with error handling and performance tracking
- X-ray logging captures execution times and crash information
- Evidence is structured using Pydantic models for validation
- Reasoning engine aggregates reliability scores for verdict calculation

---

# Evidence Extraction

**Implemented in:** `backend/app/detectors/`

Evidence extraction modules analyze the image and generate structured signals.

These modules operate independently and run in parallel using asyncio.

**Currently Implemented Detectors:**

### Spectral Analysis (`spectral.py`)
Detection of frequency artifacts often associated with generative models.
- Uses **Six-Lens Fusion Model** (ConvNeXt, FFT, SRM, Chroma, SPAI, Robustness)
- Aggregates multi-domain signals for resilient artifact detection
- Sanity-verified against local reference sets on every startup

### Metadata and Provenance (`metadata.py`)  
Analysis of file metadata and provenance signals.
- EXIF data extraction and serial number validation
- AI-generator signature detection (DALL-E, Midjourney, Adobe Firefly)
- Hardware profile consistency checking

### Noise and Texture Analysis (`noise.py`)
Comparison of image noise characteristics against expected camera sensor patterns.
- Thermal variance analysis using Laplacian convolution
- Quantitative assessment of artificial "film grain" common in high-end gen-AI
- Sensor fingerprint consistency validation

### Lighting and Physical Consistency (`lighting.py`)
Evaluation of whether lighting and shadows obey physical rules.
- Lighting consistency analysis and grayscale weight balancing
- Dynamic range evaluation for physical illumination logic
- Support for shadow/highlight geometric consistency

### Semantic and Physical Consistency (`semantic.py`)
**LLM-powered** logic evaluation of the visual scene.
- Uses Gemini/Groq vision models with high-precision prompts
- Detects non-Euclidean geometry and physical/biological logic errors
- Explicit AI watermark detection with high-confidence reliability boost

### Error Level Analysis (`ela.py`)
JPEG recompression analysis for detecting edited or spliced regions.
- Generates high-contrast ELA heatmaps
- Identifies compression artifact discontinuities
- Effective for identifying localized "inpainting" or splicing

### Open Source Intelligence (`osint.py`)
Live web grounding for real-world verification.
- **Primary:** Grounded Google Search via Gemini's integrated tools
- **Fallback:** Multi-vector DuckDuckGo scraping for viral trend identification
- Cross-references visual context with verified reporting and debunk databases

---

# Evidence Signals

**Implemented in:** `backend/app/models/evidence.py`

Every detector produces structured evidence rather than final conclusions.

**Current EvidenceSignal Structure:**
- `id`: Stable detector identifier (string)
- `name`: Human-readable signal name (string)  
- `category`: Signal category (string)
- `status`: One of `ok`, `warning`, `unavailable`, `error`
- `reliability`: Estimated reliability between `0.0` and `1.0`
- `summary`: Short summary of observations
- `observations`: List of specific observations (strings)
- `supports`: One of `authentic`, `ai_generated`, `inconclusive`, `unknown`
- `metrics`: Optional structured measurements

The goal is to capture **what was observed**, not just a verdict.

---

# Evidence Aggregation

**Implemented in:** `backend/app/core/pipeline.py`

All signals are aggregated into a unified **EvidenceProfile**.

The evidence profile represents the system's complete understanding of the image.

This profile becomes the input to the reasoning system.

The aggregation stage simply organizes and standardizes evidence without producing narrative explanations.

---

# Reasoning Layer

**Implemented in:** `backend/app/reasoning/engine.py`

A reasoning engine interprets the evidence profile and produces a human-readable explanation.

**Current Implementation:**
- Reliability scores are aggregated for `authentic` vs `ai_generated` support
- Verdict logic handles conflicting evidence with `INCONCLUSIVE` outcomes
- LLM client (Gemini/Groq) generates human-readable explanations
- Fallback explanations ensure system always produces output

The reasoning system behaves similarly to a forensic analyst:
- identifying patterns
- explaining contradictions  
- highlighting strong signals
- acknowledging uncertainty

The reasoning engine converts structured evidence into a narrative explanation.

---

# Verdict Logic

**Implemented in:** `backend/app/reasoning/engine.py`

The system supports three possible conclusions:

Likely authentic  
Likely AI-generated  
Inconclusive

**Current Verdict Algorithm:**
- Aggregate reliability scores for authentic vs AI-generated support
- If both scores > 0.4 and difference < 0.25 → INCONCLUSIVE
- If one score > 0.4 and dominates → corresponding verdict
- If scores are balanced or weak → INCONCLUSIVE

The system never forces a conclusion when signals conflict.

Inconclusive outcomes are an essential part of ethical design.

---

# Frontend Visualization

**Implemented in:** `frontend/src/App.jsx`

The user interface presents analysis results clearly and transparently.

**Current Interface Components:**
- Image upload and display
- Final verdict display with confidence indicators
- Evidence cards for each signal with reliability scores
- Detailed explanation narrative from LLM reasoning
- Signal status indicators (ok/warning/unavailable/error)
- Responsive design with modern UI framework

The interface emphasizes clarity and trust by exposing the reasoning process.

---

# Parallel Signal Processing

**Implemented in:** `backend/app/core/pipeline.py`

Evidence extraction modules run concurrently using `asyncio.gather()`.

**Current Implementation:**
- All 7 detectors execute in parallel
- Individual error handling prevents cascade failures
- Performance tracking captures execution times per detector
- X-ray logging provides detailed timing diagnostics

Parallel analysis improves responsiveness and allows the system to scale as additional detectors are added.

The architecture supports dynamic addition of new signal modules through the detector registry.

---

# Modular Design

**Implemented in:** `backend/app/detectors/registry.py`

ArgusAI maintains modular detector architecture.

**Current Implementation:**
- Base detector class (`base.py`) defines interface
- Registry pattern allows dynamic detector registration
- Each detector is independent with standardized interface
- New detectors can be added without modifying core pipeline

The architecture treats detectors as plug-in analysis modules.

This allows the system to evolve as new detection techniques emerge.

---

# Future Extension: Video

Although ArgusAI currently analyzes images, the architecture supports expansion to video analysis.

Video analysis can be achieved by applying the image pipeline to extracted frames and adding temporal consistency analysis.

Possible future signals include:

- frame-to-frame lighting consistency
- motion artifact detection
- temporal noise analysis
- facial movement realism
- lip synchronization

The core reasoning architecture remains the same.

---

# Future Extension: External Verification

The system may eventually incorporate external verification signals such as:

- reverse image search
- fact-checking databases
- open-source intelligence
- prior debunking records
- contextual verification from trusted sources

These signals should be treated as additional evidence modules.

---

# Ethical Considerations

The system must prioritize responsible analysis.

Key principles include:

- avoiding false certainty
- clearly communicating uncertainty
- exposing evidence behind conclusions
- preventing misuse through transparency

ArgusAI should help users understand evidence rather than blindly trusting automated decisions.

---

# Guiding Design Rule

ArgusAI should behave like a **forensic investigator** rather than a classification model.

The system should answer:

What evidence exists?  
What does that evidence imply?  
Where are the uncertainties?

This philosophy guides every component of the system.
## Recent Updates (2026-03-24)

- **Six‑Lens Spectral Model** – `SpectralFusionModel` now implements six parallel branches (ConvNeXt, FFT, SRM, Chroma (YCbCr), SPAI, Robustness) with a 1792‑dim fusion head.
- **Grayscale conversion** – Updated to BT.601 luma weights (`0.299, 0.587, 0.114`).
- **Environment** – `SPECTRAL_AI_INDEX=0` to match fine‑tuned model.
- **Semantic Detector** – Added confidence‑driven `supports` mapping and reliability boost to 0.9 when watermark detected.
- **Verification script** – `test_full_model.py` validates model loading and inference.
