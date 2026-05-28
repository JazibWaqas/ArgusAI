from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from PIL import Image

from ..core.config import settings
from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from .base import Detector

try:
    import torch
    from .spectral_model import SpectralFusionModel, load_state_dict_from_path
except Exception as exc:
    torch = None  # type: ignore[assignment]
    SpectralFusionModel = None  # type: ignore[assignment]
    load_state_dict_from_path = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR = str(exc)
else:
    _TORCH_IMPORT_ERROR = None


class SpectralArtifactDetector(Detector):
    id = "spectral_artifacts"
    name = "Spectral Artifacts"
    category = "spectral"

    _model: Optional[SpectralFusionModel] = None
    _model_error: Optional[str] = None
    _model_health_error: Optional[str] = None
    _model_health_notes: Optional[str] = None
    _model_health_gap: Optional[float] = None
    _resolved_ai_index: Optional[int] = None

    def _preprocess_image(self, image: Image.Image) -> torch.Tensor:
        resized = image.resize((settings.spectral_input_size, settings.spectral_input_size), Image.BICUBIC)
        arr = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)

        if settings.spectral_normalize:
            mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
            std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
            tensor = (tensor - mean) / std

        return tensor

    def _predict_probs(self, image: Image.Image) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Spectral model is not loaded.")

        tensor = self._preprocess_image(image)
        with torch.no_grad():
            logits = self._model(tensor)
            probs = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
        return probs

    def _reference_files(self, directory: str) -> list[Path]:
        path = Path(directory)
        if not path.exists() or not path.is_dir():
            return []

        allowed = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        files = [item for item in sorted(path.iterdir()) if item.is_file() and item.suffix.lower() in allowed]
        limit = max(2, settings.spectral_reference_sample_count)
        return files[:limit]

    def _run_reference_self_test(self) -> None:
        if self._model is None or self._model_health_error is not None or self._resolved_ai_index is not None:
            return

        real_files = self._reference_files(settings.spectral_reference_real_dir)
        ai_files = self._reference_files(settings.spectral_reference_ai_dir)
        if len(real_files) < 2 or len(ai_files) < 2:
            self._resolved_ai_index = settings.spectral_ai_index
            self._model_health_notes = "Reference self-test skipped because local real/AI folders were not available."
            return

        try:
            real_probs = []
            ai_probs = []
            for file_path in real_files:
                with Image.open(file_path) as image:
                    real_probs.append(self._predict_probs(image.convert("RGB")))
            for file_path in ai_files:
                with Image.open(file_path) as image:
                    ai_probs.append(self._predict_probs(image.convert("RGB")))

            real_arr = np.asarray(real_probs, dtype=np.float32)
            ai_arr = np.asarray(ai_probs, dtype=np.float32)
            best_index = settings.spectral_ai_index
            best_gap = -1.0
            collapse = False

            for candidate_index in range(real_arr.shape[1]):
                real_mean = float(real_arr[:, candidate_index].mean())
                ai_mean = float(ai_arr[:, candidate_index].mean())
                gap = ai_mean - real_mean
                real_pred_ratio = float((real_arr.argmax(axis=1) == candidate_index).mean())
                ai_pred_ratio = float((ai_arr.argmax(axis=1) == candidate_index).mean())
                is_collapsed = real_pred_ratio >= 0.95 and ai_pred_ratio >= 0.95

                if gap > best_gap:
                    best_gap = gap
                    best_index = candidate_index
                    collapse = is_collapsed

            if best_gap < 0.15 or collapse:
                self._model_health_gap = best_gap
                self._model_health_error = (
                    "Reference self-test failed: the spectral model does not separate local real and AI samples."
                )
                self._model_health_notes = (
                    f"Best class gap was {best_gap:.3f} across {len(real_files)} real and {len(ai_files)} AI reference images."
                )
                return

            self._resolved_ai_index = best_index
            if best_index != settings.spectral_ai_index:
                self._model_health_notes = (
                    f"Reference self-test corrected spectral AI index from {settings.spectral_ai_index} to {best_index}."
                )
            else:
                self._model_health_notes = (
                    f"Reference self-test passed with class gap {best_gap:.3f} using {len(real_files)} real and {len(ai_files)} AI samples."
                )
        except Exception as exc:
            self._model_health_error = f"Reference self-test crashed: {exc}"

    def _load_model(self, model_path: str) -> Optional[str]:
        if self._model is not None or self._model_error is not None:
            return self._model_error

        if torch is None or SpectralFusionModel is None or load_state_dict_from_path is None:
            self._model_error = f"PyTorch spectral runtime is unavailable: {_TORCH_IMPORT_ERROR or 'torch import failed'}"
            return self._model_error

        try:
            state = load_state_dict_from_path(model_path)
            model = SpectralFusionModel()
            missing, unexpected = model.load_state_dict(state, strict=False)
            model.eval()
            self._model = model
            if missing or unexpected:
                details = []
                if missing:
                    details.append(f"missing keys: {len(missing)}")
                if unexpected:
                    details.append(f"unexpected keys: {len(unexpected)}")
                self._model_error = "; ".join(details)
        except Exception as exc:
            self._model_error = f"Failed to load spectral model: {exc}"

        if self._model is not None:
            self._run_reference_self_test()
        return self._model_error

    async def analyze(self, image, context: Dict[str, Any]) -> EvidenceSignal:
        # Check primary path and potential relative paths if not found
        model_path = settings.spectral_model_path
        if not os.path.exists(model_path):
            # Try parent directory (common when running from backend/ folder)
            parent_path = os.path.join("..", model_path)
            if os.path.exists(parent_path):
                model_path = parent_path
            else:
                return EvidenceSignal(
                    id=self.id,
                    name=self.name,
                    category=self.category,
                    status=SignalStatus.UNAVAILABLE,
                    reliability=0.0,
                    summary="This check could not run because the spectral model is not available.",
                    what_checked="We look for hidden frequency patterns that often appear in AI-generated images.",
                    what_found="The spectral detector was unavailable for this image.",
                    why_it_matters="Without this check, we lose one useful way of spotting generation artifacts that are hard to see by eye.",
                    caveat="This does not say anything about the image itself. It only means this detector was not available.",
                    observations=[f"Expected model at {settings.spectral_model_path} or {parent_path}"],
                    supports=SignalSupport.UNKNOWN,
                    notes="Place the spectral model directory or file at the configured path.",
                )

        load_error = self._load_model(model_path)
        if self._model is None:
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.ERROR,
                reliability=0.0,
                summary="This check failed because the spectral model could not be loaded.",
                what_checked="We look for hidden frequency patterns that often appear in AI-generated images.",
                what_found="The detector crashed before it could analyze the image.",
                why_it_matters="Without this check, the final result has less information about hidden generation artifacts.",
                caveat="This is a detector failure, not evidence for or against authenticity.",
                observations=[load_error or "Unknown model loading error."],
                supports=SignalSupport.UNKNOWN,
            )

        if self._model_health_error:
            observations = [self._model_health_error]
            if self._model_health_notes:
                observations.append(self._model_health_notes)
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.ERROR,
                reliability=0.0,
                summary="The spectral detector was disabled because the loaded model failed a sanity check.",
                what_checked="We compare the loaded spectral model against small local reference sets when available.",
                what_found="This checkpoint behaved like a collapsed or misconfigured classifier during the reference self-test.",
                why_it_matters="A broken spectral model can wrongly push the whole report toward AI generation.",
                caveat="This is a model health issue, not evidence about the uploaded image.",
                observations=observations,
                metrics={
                    "circuit_breaker": True,
                    "circuit_breaker_reason": "reference_self_test_failed",
                    "gap_score": self._model_health_gap,
                },
                supports=SignalSupport.UNKNOWN,
                notes="Replace the checkpoint or align the inference model with the original training/export pipeline.",
            )

        probs = self._predict_probs(image)
        ai_index = self._resolved_ai_index if self._resolved_ai_index is not None else settings.spectral_ai_index
        ai_prob = float(probs[ai_index])
        auth_prob = float(probs[1 - ai_index]) if len(probs) > 1 else 1.0 - ai_prob
        margin = abs(ai_prob - auth_prob)

        # Build confidence label based on margin
        if margin >= 0.5:
            confidence_label = "extremely high"
        elif margin >= 0.3:
            confidence_label = "high"
        elif margin >= 0.15:
            confidence_label = "moderate"
        else:
            confidence_label = "low"

        if ai_prob >= 0.6:
            supports = SignalSupport.AI_GENERATED
            summary = (
                f"The Six-Lens model scored this image {ai_prob:.1%} AI / {auth_prob:.1%} authentic — "
                f"a {confidence_label}-confidence finding toward synthetic generation."
            )
            what_found = (
                f"All six spectral lenses — visual texture (ConvNeXt), frequency grids (FFT), sensor noise simulation (SRM), "
                f"color-space fingerprints (YCbCr), spatial reconstruction (SPAI), and robustness testing — "
                f"collectively scored this image {ai_prob:.1%} AI. "
                f"{'A score this strong' if ai_prob >= 0.80 else 'At this level'}, the majority of lenses independently flagged patterns "
                f"like periodic frequency grids and noise distributions inconsistent with any known camera sensor profile."
            )
            why_it_matters = (
                f"This model looks for patterns invisible to the human eye — buried in the pixel-level math of the image. "
                f"A {ai_prob:.1%} score means the statistical fingerprint aligns significantly more with AI generation than camera physics, "
                f"and these frequency-domain traces are very hard to remove without visibly degrading the image."
            )
        elif ai_prob <= 0.4:
            supports = SignalSupport.AUTHENTIC
            summary = (
                f"The Six-Lens model scored this image {auth_prob:.1%} authentic / {ai_prob:.1%} AI — "
                f"a {confidence_label}-confidence finding toward real camera capture."
            )
            what_found = (
                f"Across all six lenses, the model returned only {ai_prob:.1%} AI probability — consistent with real camera optics. "
                f"The SRM residuals match expected sensor noise, the FFT spectrum shows natural frequency falloff (no periodic grid artifacts), "
                f"and the SPAI reconstruction probe behaved predictably — the way natural scenes respond, not AI-synthesized regions."
            )
            why_it_matters = (
                f"A {auth_prob:.1%} authenticity score means the image's deepest mathematical structure is consistent with physical lens optics and silicon sensor physics. "
                f"AI generators produce fundamentally different frequency-domain statistics than cameras, and those differences persist even when the image looks visually convincing."
            )
        else:
            supports = SignalSupport.INCONCLUSIVE
            summary = (
                f"The Six-Lens model returned a split result: {ai_prob:.1%} AI vs {auth_prob:.1%} authentic — "
                f"a margin of only {margin:.1%}, too narrow for a confident read."
            )
            what_found = (
                f"The six lenses produced a contested split: {ai_prob:.1%} AI vs {auth_prob:.1%} authentic, with a margin of just {margin:.1%}. "
                f"This typically means either a high-quality AI image that passed some lenses but not others, "
                f"or a real photo that's been compressed or resized enough to partially erase its original frequency-domain fingerprint."
            )
            why_it_matters = (
                f"A split result at {ai_prob:.1%}/{auth_prob:.1%} is itself forensically meaningful — clearly authentic images typically score 20-35% AI, "
                f"and clearly AI images 75-99%. This middle zone suggests the image's statistical fingerprint has been partially obscured, "
                f"making the other detectors especially important."
            )

        observations = [
            f"Six-Lens fusion result — AI score: {ai_prob:.4f} ({ai_prob:.1%}), Authentic score: {auth_prob:.4f} ({auth_prob:.1%}).",
            f"Score margin: {margin:.4f} — the gap between the two class probabilities. Margins above 0.30 are considered high-confidence.",
            f"Confidence tier: {confidence_label} (margin {margin:.2f}).",
            f"Lenses applied: (1) ConvNeXt semantic texture, (2) FFT frequency domain, (3) SRM sensor noise residuals, "
            f"(4) YCbCr chroma channel analysis, (5) SPAI spatial predictability, (6) Robustness adversarial probe.",
            f"Fusion head input dimensions: 1792 (all six lens outputs concatenated).",
            f"AI class index used: {ai_index} (configured: {settings.spectral_ai_index}{'.' if ai_index == settings.spectral_ai_index else f', overridden by reference self-test.'}).",
        ]
        if load_error:
            observations.append(f"Model load notes: {load_error}")
        if self._model_health_notes:
            observations.append(self._model_health_notes)

        return EvidenceSignal(
            id=self.id,
            name=self.name,
            category=self.category,
            status=SignalStatus.OK,
            reliability=0.7,
            summary=summary,
            what_checked=(
                "We passed this image through a Six-Lens forensic fusion model that simultaneously analyzes: "
                "visual texture patterns (ConvNeXt), hidden frequency grids (FFT), sensor noise residuals (SRM), "
                "color-space fingerprints (YCbCr/Chroma), spatial reconstruction behavior (SPAI), "
                "and stability under mild perturbation (Robustness). All six outputs are concatenated and scored by a trained fusion classifier."
            ),
            what_found=what_found,
            why_it_matters=why_it_matters,
            caveat=(
                "Heavy JPEG compression, aggressive resizing, or strong image filters can partially destroy the frequency-domain signals this model depends on, "
                "potentially softening a confident AI detection into an inconclusive result. "
                "Conversely, very new or unusual AI generators not present in training data may produce lower-than-expected scores."
            ),
            observations=observations,
            metrics={"ai_probability": ai_prob, "auth_probability": auth_prob, "margin": margin, "confidence_label": confidence_label},
            confidence=max(ai_prob, auth_prob),
            supports=supports,
            notes="Six-Lens spectral fusion model: ConvNeXt + FFT + SRM + Chroma + SPAI + Robustness, 1792-dim fusion head.",
        )

