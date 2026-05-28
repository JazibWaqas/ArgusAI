from __future__ import annotations

from typing import Any, Dict

import numpy as np

from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from .base import Detector


class LightingConsistencyDetector(Detector):
    id = "lighting_consistency"
    name = "Lighting Physics & Contrast Geometry"
    category = "lighting"

    async def analyze(self, image, context: Dict[str, Any]) -> EvidenceSignal:
        arr = np.asarray(image.convert("L"), dtype=np.float32)

        dynamic_range = float(arr.max() - arr.min())
        brightest = float(arr.max())
        darkest = float(arr.min())
        mean_brightness = float(arr.mean())
        clipped_highlights = float(np.mean(arr >= 253.0))
        crushed_blacks = float(np.mean(arr <= 2.0))

        windows = [arr[i:i+64, j:j+64] for i in range(0, arr.shape[0]-64, 64) for j in range(0, arr.shape[1]-64, 64)]
        if windows:
            window_means = [np.mean(w) for w in windows]
            global_contrast_variance = float(np.var(window_means))
            local_stds = [np.std(w) for w in windows]
            mean_local_std = float(np.mean(local_stds))
            flattest_region = float(min(local_stds))
        else:
            global_contrast_variance = 0.0
            mean_local_std = 0.0
            flattest_region = 0.0

        observations = [
            f"Dynamic range: {dynamic_range:.0f}/255 (darkest pixel: {darkest:.0f}, brightest: {brightest:.0f})",
            f"Mean scene brightness: {mean_brightness:.1f}/255",
            f"Highlight clipping: {clipped_highlights*100:.3f}% of pixels at or above 253/255 (blown highlights)",
            f"Shadow crushing: {crushed_blacks*100:.3f}% of pixels at or below 2/255 (pure black, no shadow detail)",
            f"Regional contrast variance across 64x64 blocks: {global_contrast_variance:.1f} (how unevenly light is distributed across the scene)",
            f"Mean local texture per region: {mean_local_std:.2f} | Flattest region std: {flattest_region:.2f}",
            "Key principle: real camera sensors obey the exposure triangle - they cannot simultaneously preserve highlights and shadows across a wide dynamic range without clipping at least one end.",
        ]

        supports = SignalSupport.UNKNOWN
        reliability = 0.4
        is_perfectly_flat = clipped_highlights < 0.001 and crushed_blacks < 0.001 and dynamic_range > 150

        if is_perfectly_flat and global_contrast_variance < 1000:
            observations.append(
                f"CRITICAL: Dynamic range is {dynamic_range:.0f}/255 but clipping is essentially zero on both ends "
                f"({clipped_highlights*100:.4f}% highlights, {crushed_blacks*100:.4f}% shadows). "
                "A real camera sensor cannot achieve this - it will always sacrifice detail at one extreme. "
                f"Regional contrast variance ({global_contrast_variance:.1f}) is also unnaturally low, confirming HDR-perfect light distribution."
            )
            supports = SignalSupport.AI_GENERATED
            reliability = 0.65
            summary = (
                f"The lighting looks physically impossible for a real camera: dynamic range of {dynamic_range:.0f}/255 "
                f"with only {clipped_highlights*100:.3f}% blown highlights and {crushed_blacks*100:.3f}% crushed shadows."
            )
            what_found = (
                f"This image spans {dynamic_range:.0f}/255 of tonal range but loses virtually no detail at either extreme - "
                f"{clipped_highlights*100:.3f}% clipped highlights and {crushed_blacks*100:.3f}% crushed shadows. "
                "Real camera sensors physically cannot do this: they must sacrifice highlight or shadow detail in high-contrast scenes. "
                f"The regional contrast variance of {global_contrast_variance:.1f} is also suspiciously low, meaning light is distributed unnaturally evenly across the entire scene."
            )
            why_it_matters = (
                "This 'perfect HDR' profile is a known fingerprint of AI generation. Diffusion models compute light mathematically "
                "and don't face the physical saturation limits that real sensors do. A camera would always clip in one or both directions here."
            )
        elif clipped_highlights > 0.02 or crushed_blacks > 0.05:
            observations.append(
                f"Physical clipping detected: {clipped_highlights*100:.2f}% of pixels blown to near-white, "
                f"{crushed_blacks*100:.2f}% crushed to near-black. "
                "This is the expected consequence of a real sensor hitting its dynamic range limit in a high-contrast scene."
            )
            supports = SignalSupport.AUTHENTIC
            reliability = 0.55
            summary = (
                f"The image shows real camera clipping - {clipped_highlights*100:.2f}% blown highlights and {crushed_blacks*100:.2f}% crushed shadows - "
                "the physical trace of a sensor that ran out of dynamic range."
            )
            what_found = (
                f"{clipped_highlights*100:.2f}% of pixels are burned to near-white and {crushed_blacks*100:.2f}% are crushed to near-black. "
                "This is the hallmark of a real camera encountering more contrast than its sensor could handle, "
                "for example, a bright sky against a shaded subject. "
                "AI generators don't face physical saturation limits, so they almost never produce this kind of natural clipping."
            )
            why_it_matters = (
                "Clipping is not a mistake - it's a physical inevitability when a real sensor meets a high-contrast scene. "
                "Because AI computes light mathematically, it rarely produces authentic-looking sensor clipping, making its presence here a meaningful signal for authenticity."
            )
        else:
            observations.append(
                f"All metrics in mid-range: {clipped_highlights*100:.3f}% highlights clipped, {crushed_blacks*100:.3f}% shadows crushed, "
                f"dynamic range {dynamic_range:.0f}/255, regional variance {global_contrast_variance:.1f}. "
                "Consistent with a well-exposed real photo, a tone-mapped edit, or a high-quality AI image - indistinguishable from this signal alone."
            )
            supports = SignalSupport.INCONCLUSIVE
            reliability = 0.3
            summary = (
                f"The lighting is balanced and well-behaved ({dynamic_range:.0f}/255 range, {mean_brightness:.1f}/255 mean, "
                f"{clipped_highlights*100:.3f}% clipping) - matching both a well-exposed real photo and a capable AI generator."
            )
            what_found = (
                f"The image has a {dynamic_range:.0f}/255 dynamic range, {mean_brightness:.1f}/255 mean brightness, "
                f"and only {clipped_highlights*100:.3f}% clipped highlights with {crushed_blacks*100:.3f}% crushed shadows. "
                "This balanced exposure is realistic-looking but not diagnostic - it fits equally well for a careful real photograph and a modern AI generator."
            )
            why_it_matters = (
                "Lighting is most useful when it's either suspiciously perfect (AI) or clearly clipping (real). "
                "A balanced middle-ground doesn't give us enough to work with, so this signal defers to others."
            )

        return EvidenceSignal(
            id=self.id,
            name=self.name,
            category=self.category,
            status=SignalStatus.OK,
            reliability=reliability,
            summary=summary,
            what_checked="We measured how this image's brightness, contrast, and exposure behave - specifically whether they follow the physical laws that govern real camera sensors.",
            what_found=what_found,
            why_it_matters=why_it_matters,
            caveat="HDR post-processing, tone mapping, strong flash, and professional retouching can all alter exposure profiles - introducing 'AI-like' qualities into real photos or vice versa.",
            observations=observations,
            metrics={
                "dynamic_range": dynamic_range,
                "brightest_pixel": brightest,
                "darkest_pixel": darkest,
                "mean_brightness": mean_brightness,
                "clipped_highlights": clipped_highlights,
                "crushed_blacks": crushed_blacks,
                "contrast_variance": global_contrast_variance,
                "mean_local_std": mean_local_std,
                "flattest_region_std": flattest_region,
            },
            supports=supports,
            notes="Evaluates optical exposure realism. Generative models rarely replicate true physical clipping.",
        )
