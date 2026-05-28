from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, Dict

import numpy as np
from PIL import Image, ImageChops

from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from .base import Detector


class ErrorLevelAnalysisDetector(Detector):
    id = "error_level_analysis"
    name = "Error Level Analysis (ELA)"
    category = "forensic"

    async def analyze(self, image, context: Dict[str, Any]) -> EvidenceSignal:
        original = image.convert("RGB")
        width, height = original.size

        buffer = BytesIO()
        jpeg_quality = 90
        original.save(buffer, format="JPEG", quality=jpeg_quality)
        buffer.seek(0)
        recompressed = Image.open(buffer)

        diff = ImageChops.difference(original, recompressed)
        diff_np = np.asarray(diff, dtype=np.float32)

        max_diff = float(diff_np.max())
        mean_diff = float(diff_np.mean())
        std_diff = float(diff_np.std())

        h, w = diff_np.shape[:2]
        quadrants = {
            "top_left": diff_np[:h//2, :w//2],
            "top_right": diff_np[:h//2, w//2:],
            "bottom_left": diff_np[h//2:, :w//2],
            "bottom_right": diff_np[h//2:, w//2:],
        }
        quad_means = {name: float(q.mean()) for name, q in quadrants.items()}
        max_quad_mean = max(quad_means.values())
        min_quad_mean = min(quad_means.values())
        quad_spread = max_quad_mean - min_quad_mean
        hotspot_ratio = float(np.mean(diff_np > 30.0))

        scale = 1.0
        if max_diff > 0:
            scale = 255.0 / max_diff
        scaled = np.clip(diff_np * scale, 0, 255).astype(np.uint8)
        ela_image = Image.fromarray(scaled)

        ela_buffer = BytesIO()
        ela_image.save(ela_buffer, format="PNG")
        ela_base64 = base64.b64encode(ela_buffer.getvalue()).decode("utf-8")

        observations = [
            f"Image: {width}x{height}px | JPEG recompressed at quality {jpeg_quality}",
            f"Mean ELA residual: {mean_diff:.2f} | Max residual: {max_diff:.2f} | Std deviation: {std_diff:.2f}",
            f"Quadrant residuals - TL: {quad_means['top_left']:.2f}, TR: {quad_means['top_right']:.2f}, BL: {quad_means['bottom_left']:.2f}, BR: {quad_means['bottom_right']:.2f}",
            f"Quadrant spread (highest minus lowest): {quad_spread:.2f} - measures how unevenly compression error is distributed across image regions",
            f"Hotspot coverage: {hotspot_ratio*100:.2f}% of pixels have residual above 30/255 - elevated compression stress",
            f"ELA amplification scale: {scale:.1f}x (higher = lower total ELA energy in the original)",
            "How ELA works: After re-saving at a fixed quality, areas with a different original compression history show higher residuals. Composited or edited regions often stand out as bright hotspots.",
        ]

        if quad_spread > 8.0 and hotspot_ratio > 0.05:
            observations.append(
                f"Regional inconsistency flagged: quadrant spread of {quad_spread:.2f} and {hotspot_ratio*100:.2f}% hotspot coverage. "
                "Different areas of the image appear to have different compression histories - a classic sign of compositing or copy-paste editing."
            )
            supports = SignalSupport.UNKNOWN
            reliability = 0.25
            summary = (
                f"The ELA map shows significant regional unevenness - a {quad_spread:.2f}/255 spread across quadrants "
                f"and {hotspot_ratio*100:.2f}% of pixels with elevated residuals - suggesting inconsistent compression history."
            )
            what_found = (
                f"Compression stress varies by {quad_spread:.2f} between the most and least stressed quadrants of the image. "
                f"{hotspot_ratio*100:.2f}% of pixels have elevated ELA residuals (above 30/255), creating distinct hotspots. "
                "This pattern, where different image regions have mismatched compression histories, is typical of composited or edited images."
            )
            why_it_matters = (
                "ELA detects editing and compositing, not AI generation directly. "
                "These hotspots suggest the image may have been assembled from multiple sources or retouched - a relevant flag regardless of origin."
            )
        elif mean_diff < 1.5 and max_diff < 20.0:
            observations.append(
                f"Near-zero ELA residual: mean {mean_diff:.2f}, max {max_diff:.2f}. "
                f"The image was likely originally saved at a quality close to our test quality of {jpeg_quality}, making ELA unable to distinguish anything meaningful. "
                f"Scale factor of {scale:.1f}x confirms near-zero actual energy - the heatmap is essentially amplified noise."
            )
            supports = SignalSupport.UNKNOWN
            reliability = 0.1
            summary = (
                f"ELA found essentially no compression residual (mean: {mean_diff:.2f}, max: {max_diff:.2f}). "
                f"The image's original quality setting is too close to the test quality for ELA to produce meaningful results."
            )
            what_found = (
                f"Re-saving this image at quality {jpeg_quality} produced a mean residual of only {mean_diff:.2f} - effectively nothing. "
                f"The amplification scale needed to visualize the heatmap is {scale:.1f}x, confirming the actual ELA energy is negligible. "
                "ELA is blind to images saved at the same quality as the test - no evidence can be extracted here."
            )
            why_it_matters = (
                "A zero residual means ELA has nothing to report - not that the image is clean, just that this particular test found nothing actionable. "
                "Other detectors carry the forensic weight here."
            )
        else:
            observations.append(
                f"Moderate, uniform ELA profile: mean {mean_diff:.2f}, spread {quad_spread:.2f}, {hotspot_ratio*100:.2f}% hotspots. "
                "No strong evidence of compositing or mismatched compression history - the image has a consistent save history across all regions."
            )
            supports = SignalSupport.UNKNOWN
            reliability = 0.25
            summary = (
                f"The ELA map shows moderate, fairly uniform compression residuals (mean: {mean_diff:.2f}, quadrant spread: {quad_spread:.2f}). "
                "No editing seams or compositing artifacts were detected."
            )
            what_found = (
                f"Re-saving at quality {jpeg_quality} produced a mean residual of {mean_diff:.2f} with a quadrant spread of only {quad_spread:.2f}. "
                f"The compression stress is consistent across all four quadrants, and only {hotspot_ratio*100:.2f}% of pixels show elevated residuals. "
                "This uniform profile suggests the image has a consistent compression history - no obvious signs of region-level editing or compositing."
            )
            why_it_matters = (
                "A uniform ELA profile removes one red flag - there are no obvious editing seams. "
                "However, ELA does not tell us whether the image is AI-generated, only that it has not been obviously composited. "
                "The other detectors handle the AI vs. real question."
            )

        return EvidenceSignal(
            id=self.id,
            name=self.name,
            category=self.category,
            status=SignalStatus.OK,
            reliability=reliability,
            summary=summary,
            what_checked=(
                f"We re-saved this {width}x{height} image at JPEG quality {jpeg_quality} and measured the pixel-level difference between the original and re-compressed version. "
                "Regions with different original compression settings, or composited from different sources, appear as bright hotspots in the resulting error map."
            ),
            what_found=what_found,
            why_it_matters=why_it_matters,
            caveat=(
                "ELA detects editing and compression inconsistency, not AI generation. "
                "Social media uploads, repeated saves, and WhatsApp forwarding all degrade this test. "
                "It's treated as a weak supporting check."
            ),
            observations=observations,
            metrics={
                "ela_mean": mean_diff,
                "ela_max": max_diff,
                "ela_std": std_diff,
                "ela_scale": scale,
                "ela_quality": jpeg_quality,
                "quadrant_means": quad_means,
                "quadrant_spread": quad_spread,
                "hotspot_ratio": hotspot_ratio,
                "image_width": width,
                "image_height": height,
                "ela_image_base64": ela_base64,
            },
            supports=supports,
            notes="ELA highlights compression inconsistencies; interpret alongside other signals.",
        )
