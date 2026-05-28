from __future__ import annotations

from typing import Any, Dict

import numpy as np

from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from .base import Detector


class NoisePatternDetector(Detector):
    id = "noise_pattern_analysis"
    name = "Thermal Noise & Sensor Consistency"
    category = "noise"

    async def analyze(self, image, context: Dict[str, Any]) -> EvidenceSignal:
        arr = np.asarray(image.convert("L"), dtype=np.float32)

        mean = float(arr.mean())
        variance = float(arr.var())
        std_dev = float(np.sqrt(variance))

        diff_y = np.abs(np.diff(arr, axis=0))
        diff_x = np.abs(np.diff(arr, axis=1))
        high_freq_overall = float((np.mean(diff_y) + np.mean(diff_x)) / 2.0)

        windows = [arr[i:i+32, j:j+32] for i in range(0, arr.shape[0]-32, 32) for j in range(0, arr.shape[1]-32, 32)]
        if windows:
            window_vars = [np.var(w) for w in windows]
            dead_zone_ratio = sum(1 for v in window_vars if v < 2.0) / len(window_vars)
            min_window_var = float(min(window_vars))
            max_window_var = float(max(window_vars))
        else:
            dead_zone_ratio = 0.0
            min_window_var = 0.0
            max_window_var = 0.0

        observations = [
            f"Global pixel variance: {variance:.1f} | Mean brightness: {mean:.1f}/255 | Std deviation: {std_dev:.1f}",
            f"High-frequency spatial energy: {high_freq_overall:.2f} (measures abruptness of pixel transitions)",
            f"Smooth dead-zones: {dead_zone_ratio*100:.1f}% of 32x32 blocks have near-zero variance (< 2.0 threshold)",
            f"Block variance range: {min_window_var:.1f} (flattest region) to {max_window_var:.1f} (most textured region)",
            "Interpretation: real camera sensors cannot suppress noise below a physical floor even in out-of-focus areas. AI generators often produce blocks with variance < 2.0 because they sample from a smooth latent space.",
        ]

        supports = SignalSupport.UNKNOWN
        reliability = 0.4

        if dead_zone_ratio > 0.4 and high_freq_overall < 4.0:
            observations.append(
                f"CRITICAL: {dead_zone_ratio*100:.0f}% of the image surface is mathematically flat - no camera sensor operating at any ISO produces this. "
                f"Spatial energy of {high_freq_overall:.2f} further confirms unnaturally gentle pixel transitions throughout."
            )
            supports = SignalSupport.AI_GENERATED
            reliability = 0.65
            summary = (
                f"The sensor noise test found that {dead_zone_ratio*100:.0f}% of this image is perfectly smooth "
                "- a physical impossibility for any real camera."
            )
            what_found = (
                f"{dead_zone_ratio*100:.0f}% of pixel blocks have near-zero internal variance, meaning they're completely flat at the sub-pixel level. "
                "Real cameras always produce baseline photon noise everywhere, even in blurry areas - this image doesn't. "
                f"Spatial energy ({high_freq_overall:.2f}) is also atypically low, confirming the transitions are unnaturally smooth throughout."
            )
            why_it_matters = (
                "This specific combination - widespread flatness plus low spatial energy - is a documented fingerprint of diffusion-model generation, "
                "because AI samples from a mathematically smooth distribution rather than capturing real-world photon chaos."
            )
        elif variance > 1000.0 and high_freq_overall > 15.0:
            observations.append(
                f"Heavy chaotic noise: variance {variance:.1f}, spatial energy {high_freq_overall:.2f}. "
                "Consistent with high-ISO real photography; artificial post-grain can occasionally mimic this profile."
            )
            supports = SignalSupport.AUTHENTIC
            reliability = 0.35
            summary = (
                f"The image shows heavy, chaotic grain (variance {variance:.1f}, energy {high_freq_overall:.2f}) "
                "consistent with real high-ISO camera photography."
            )
            what_found = (
                f"The pixel variance is {variance:.1f} and spatial energy {high_freq_overall:.2f} - both well above what we typically see in AI output. "
                "This level of noise chaos is most consistent with a real camera in low-light or fast-shutter conditions. "
                "Artificially added grain is possible but would need to match this energy profile precisely."
            )
            why_it_matters = (
                "AI generators struggle to produce this quality of authentic noise chaos - they tend to be either too smooth or add grain in a geometrically uniform way. "
                "This profile leans authentic, though grain filters prevent certainty."
            )
        elif dead_zone_ratio < 0.05 and variance > 50.0:
            observations.append(
                f"Subtle uniform grain across all focal regions: {dead_zone_ratio*100:.1f}% smooth blocks, variance {variance:.1f}. "
                "Consistent with base-ISO camera capture through an optical low-pass filter."
            )
            supports = SignalSupport.AUTHENTIC
            reliability = 0.55
            summary = (
                f"The image shows consistent, subtle grain in nearly all regions ({dead_zone_ratio*100:.1f}% smooth blocks, variance {variance:.1f}) "
                "- the expected fingerprint of a real camera sensor."
            )
            what_found = (
                f"Only {dead_zone_ratio*100:.1f}% of pixel blocks are flat - the rest carry a consistent, fine-grained texture at the sub-pixel level. "
                "This is the natural noise floor left by photon shot noise and thermal read noise on real camera sensors. "
                f"The variance of {variance:.1f} is healthy: present but controlled, suggesting base-ISO capture with standard noise reduction."
            )
            why_it_matters = (
                "Uniform, subtle grain that's present everywhere but never overwhelming is genuinely difficult for AI to replicate convincingly. "
                "This pattern - real grain without being suspiciously chaotic - is one of the stronger authentic fingerprints this test can find."
            )
        else:
            observations.append(
                f"All metrics in ambiguous mid-range: variance {variance:.1f}, dead-zones {dead_zone_ratio*100:.1f}%, energy {high_freq_overall:.2f}. "
                "Likely caused by heavy JPEG compression, resizing, or AI output with added noise."
            )
            supports = SignalSupport.INCONCLUSIVE
            reliability = 0.2
            summary = (
                f"The noise profile is ambiguous - variance {variance:.1f}, {dead_zone_ratio*100:.1f}% smooth blocks - "
                "midrange values that could belong to either a compressed real photo or a noise-augmented AI image."
            )
            what_found = (
                f"The image has variance {variance:.1f} and {dead_zone_ratio*100:.1f}% flat blocks - neither extreme enough to trigger a clear verdict. "
                "This ambiguity typically means the image has been compressed, resized, or otherwise processed in a way that erased the original noise fingerprint."
            )
            why_it_matters = (
                "When noise falls in the middle range, it can belong to either side - meaning this signal cannot meaningfully contribute to the verdict. "
                "The other detectors carry more weight here."
            )

        return EvidenceSignal(
            id=self.id,
            name=self.name,
            category=self.category,
            status=SignalStatus.OK,
            reliability=reliability,
            summary=summary,
            what_checked="We analyzed the sub-pixel noise texture of this image to see whether it matches the physical noise signature real camera sensors produce at any ISO.",
            what_found=what_found,
            why_it_matters=why_it_matters,
            caveat="Heavy compression, denoising, upscaling, or added grain filters can all change the noise profile independently of whether the image was generated or photographed.",
            observations=observations,
            metrics={
                "mean": mean,
                "variance": variance,
                "std_dev": std_dev,
                "high_freq_energy": high_freq_overall,
                "dead_zone_ratio": dead_zone_ratio,
                "block_variance_min": min_window_var,
                "block_variance_max": max_window_var,
            },
            supports=supports,
            notes="Analyzes physical thermal discrepancies; AI often fails to render true Gaussian ISO sensor noise in out-of-focus areas.",
        )
