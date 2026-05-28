# ArgusAI

Explainable forensic verification for AI-generated images.

## Current Status

**✅ Fully Functional Implementation**
- 7 forensic detectors with parallel processing
- FastAPI backend with async pipeline
- React chat UI (analyze + optional context, follow-up questions)
- In-memory sessions for chat and last report
- OSINT: Gemini Google Search grounding when enabled, DuckDuckGo fallback
- LLM-powered reasoning (Gemini/Groq)
- Evidence-based explanations
- Each signal includes `verdict_influence_percent`: share of total weighted evidence mass after reasoning (UI bar), not raw detector reliability alone
- X-ray performance logging

## Quick start

### Backend Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
```

Copy environment values and add API keys as needed:

```powershell
Copy-Item .env.example .env
```

Run the backend:

```powershell
.\.venv\Scripts\uvicorn backend.app.main:app --reload
```

### Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

Set the API URL if needed:

```
VITE_API_BASE=http://localhost:8000
```

## Deploy on Render

This repo includes `render.yaml` (Blueprint): one **Python web service** (`argusai-backend`) and one **static site** (`argusai-frontend`). Connect the repo and apply the blueprint from your Render account (sign-in and Git access are required).

1. Push the repo to GitHub (or GitLab/Bitbucket that Render supports).
2. In [Render](https://dashboard.render.com): **New** → **Blueprint** → connect the repository → apply `render.yaml`.
3. On the **backend** service, open **Environment** and add secrets (not committed to git): at minimum `GEMINI_API_KEY` and usually `GROQ_API_KEY` for full behavior. See **API Configuration** above. Redeploy after saving.
4. The static site build uses `VITE_API_BASE=https://argusai-backend.onrender.com` (see `render.yaml`). If you **rename** the backend service, set `VITE_API_BASE` on the static site to `https://<your-backend-service-name>.onrender.com` and redeploy the frontend.

**Notes:** Free instances sleep when idle (cold start). PyTorch plus the spectral model can be tight on memory; if the backend crashes on analyze, upgrade the web service plan or consider hosting the spectral model elsewhere. Ensure `argusai_fuse_best` (directory checkpoint) or a `.pth` weight file is present where `SPECTRAL_MODEL_PATH` points; large checkpoints can use Git LFS or an external asset if the repo should stay small.

Render’s default Python is often **3.14+**; `pydantic-core` may then build from source (Rust) and fail on their builders. This repo includes **`.python-version`** (`3.12`) so pip installs wheels. Alternatively set **`PYTHON_VERSION`** on the web service to a full version like `3.12.8` (overrides the file).

## API (testing)

- `POST /sessions` — create a session id (in-memory).
- `POST /sessions/{session_id}/analyze` — multipart form: `file` (image), optional `context` (user text for OSINT and pipeline).
- `POST /sessions/{session_id}/messages` — JSON `{ "message": "..." }` follow-up about the last report (requires a prior analyze in that session).
- `POST /analyze` — multipart: `file`, optional `context` (same pipeline as above, no session).

## Implemented Detectors

The system currently runs 7 parallel forensic detectors:

1. **Spectral Analysis** - CNN-based frequency artifact detection
2. **Metadata Analysis** - EXIF data and provenance verification  
3. **Noise Pattern Analysis** - Thermal noise and sensor consistency
4. **Lighting Consistency** - Physical lighting and shadow analysis
5. **Semantic Analysis** - LLM-powered logical inconsistency detection
6. **Error Level Analysis** - JPEG compression artifact analysis
7. **OSINT Verification** - Grounded Google Search (Gemini tool) when enabled, else DuckDuckGo + LLM synthesis

## Spectral model setup

The spectral model is expected as a directory (default: `argusai_fuse_best/`) containing the PyTorch
state dictionary files. Install PyTorch CPU with:

```powershell
.\.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Update `.env` if your model path differs:

```
SPECTRAL_MODEL_PATH=argusai_fuse_best
```

Before trusting a new checkpoint, validate it against local real/AI folders:

```powershell
.\.venv\Scripts\python scripts\validate_spectral_model.py
```

Full-folder evaluation (local weights only, no API keys): runs `SpectralFusionModel` on every image under `Images Dataset/Real Images` and `Images Dataset/AI Images`, writes `summary.json`, `report.txt`, and figures (`confusion_matrix.png`, `prob_ai_histogram.png`, `roc.png`) to `spectral_eval_out/` by default:

```powershell
.\.venv\Scripts\python scripts\evaluate_spectral_dataset.py
```

The backend now also runs a small reference self-test when local real/AI folders are available. If the spectral checkpoint behaves like a one-class model, the detector disables itself instead of influencing the final verdict.

## API Configuration

- `GEMINI_API_KEY` — **Vision + structured tasks**: semantic detector (image JSON), OSINT query generation, OSINT synthesis when not using grounding, and **grounded OSINT** (`google_search` tool on `GEMINI_GROUNDING_MODEL`). In `.env` you can repeat `GEMINI_API_KEY=` on multiple lines (one key per line); the client rotates on HTTP 429. With no `.env` (e.g. Render), use one key in the service environment.
- `GEMINI_GROUNDING_MODEL` — Model for OSINT with Google Search. Recommended: `gemini-3-flash-preview`.
- `GEMINI_FALLBACK_MODEL` — Automatic Gemini fallback used when the primary model name is unavailable for a request. Recommended fallback: `gemini-2.5-flash`.
- `OSINT_USE_GROUNDING` — Set to `0` to use DuckDuckGo + Gemini synthesis instead of grounded search.
- `GROQ_API_KEY` — **Final report narrative** (Investigator’s Summary): default provider is Groq (`LLM_EXPLANATION_PROVIDER=groq`) for longer, clearer prose. Chat follow-ups use Groq first when this is set to `groq`.
- `LLM_EXPLANATION_PROVIDER` — `groq` (default) or `gemini` for the main written explanation only.
- `LLM_EXPLANATION_MAX_TOKENS` — Cap for that narrative (default `900`).

## Notes

- Keep API keys only in environment variables or your host’s secret store. The backend calls Gemini with the `x-goog-api-key` header (not `?key=` in the URL) so HTTP client error text does not embed the key. Error strings shown to users or written into reports are still scrubbed as a second line of defense. `.gitignore` only skips `logs/xray/` (high-volume traces), `spectral_eval_out/`, frontend build dirs, and secrets—spectral weights and shared datasets can be committed; use Git LFS if files are very large.
- If any Gemini key was ever pushed in a file or CI log, revoke it in Google AI Studio and create a new key; git history may still contain old material until rewritten.
- If `GEMINI_API_KEY` is not set, the semantic detector and Gemini-dependent OSINT paths are degraded or unavailable.
- If `GROQ_API_KEY` is not set while `LLM_EXPLANATION_PROVIDER=groq`, the main narrative falls back to the built-in template (or set provider to `gemini` if you only have Gemini).
- The spectral model loads from `SPECTRAL_MODEL_PATH` (default `argusai_fuse_best/`).
- `GET /health` now exposes non-secret runtime diagnostics including selected Gemini/Groq models, key availability, detector registration, and the configured spectral model path.
- ELA heatmaps are generated as part of the forensic signals and included in the response.
- All detectors run in parallel with performance tracking logged to `logs/xray/`.
- The system produces three possible verdicts: `LIKELY_AUTHENTIC`, `LIKELY_AI_GENERATED`, or `INCONCLUSIVE`.

## Recent Updates (2026-03-24)

- **Chat UI + sessions** — Frontend uses `POST /sessions` and session-scoped analyze; optional context field; follow-up messages against the last report.
- **Pipeline context** — Optional `user_context` is passed to detectors (OSINT uses it for grounding and DDG queries).
- **OSINT grounding** — Primary path uses Gemini `google_search` tool + JSON synthesis; falls back to DuckDuckGo if grounding fails or `OSINT_USE_GROUNDING=0`.
- **Six‑Lens Spectral Model** – `SpectralFusionModel` now implements six parallel branches (ConvNeXt, FFT, SRM, Chroma (YCbCr), SPAI, Robustness) and a 1792‑dim fusion head. The model loads cleanly from `argusai_fuse_best/`.
- **Grayscale conversion** – Uses BT.601 luma weights (`0.299, 0.587, 0.114`) instead of uniform ones.
- **Environment** – `SPECTRAL_AI_INDEX` should be `1` because the current fine-tuned model uses `0=Real, 1=AI`.
- **Semantic Detector** – LLM prompt now explicitly checks for AI watermarks; confidence‑driven `supports` mapping added.
- **Reliability weighting** – Semantic signal reliability boosts to `0.9` when confidence > 0.9 (e.g., watermark detection).
- **Verification script** – `test_full_model.py` validates weight loading and forward pass.
