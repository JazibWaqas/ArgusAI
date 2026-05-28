from __future__ import annotations

import json
from typing import Any, Dict

from PIL import ExifTags

from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from .base import Detector


class MetadataDetector(Detector):
    id = "metadata_analysis"
    name = "Metadata & Provenance"
    category = "metadata"

    async def analyze(self, image, context: Dict[str, Any]) -> EvidenceSignal:
        exif = {}
        try:
            raw_exif = image.getexif()
            if raw_exif:
                for key, value in raw_exif.items():
                    tag = ExifTags.TAGS.get(key, str(key))
                    # Safely convert arbitrary objects (like IFDRational) to string
                    exif[tag] = str(value)
        except Exception as exc:
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.ERROR,
                reliability=0.0,
                summary="This metadata check failed before it could read the file information.",
                what_checked="We checked the image file for camera, software, and EXIF information.",
                what_found="The metadata could not be read successfully.",
                why_it_matters="Metadata can sometimes show whether a file came from a real camera, editing software, or a generative tool.",
                caveat="A metadata error is not evidence for or against AI generation by itself.",
                observations=[f"EXIF extraction raised an exception: {exc}"],
                supports=SignalSupport.UNKNOWN,
            )

        observations = []
        supports = SignalSupport.UNKNOWN
        reliability = 0.2
        what_found = "The file did not provide a clear creation trail yet."
        why_it_matters = "Metadata is one useful clue about provenance, but it is rarely enough on its own."

        if not exif:
            observations.append("The file contains no EXIF metadata, so provenance clues are limited.")
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.WARNING,
                reliability=0.3,
                summary="The file does not contain any usable metadata.",
                what_checked="We checked whether the file still carries camera or software information.",
                what_found="This image has no EXIF metadata at all, so we cannot see what device or software created it.",
                why_it_matters="Missing metadata removes a useful source of provenance, but it does not automatically mean the image is AI-generated.",
                caveat="Many social media platforms strip metadata during upload, so this signal is weak on its own.",
                observations=observations,
                metrics={"exif_count": 0},
                supports=SignalSupport.UNKNOWN,
                notes="Missing metadata is common in social media but highly suspect in forensic analysis."
            )

        make = exif.get("Make", "").lower()
        model = exif.get("Model", "").lower()
        software = exif.get("Software", "").lower()

        # Generative Engine Fingerprints
        ai_engines = ["midjourney", "dall-e", "stable diffusion", "openai", "comfyui", "automatic1111"]
        is_ai_stamped = any(engine in software for engine in ai_engines) or any(engine in make or engine in model for engine in ai_engines)

        if is_ai_stamped:
            observations.append(f"Metadata explicitly references a generative tool ({software or make}).")
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.OK,
                reliability=0.95,
                summary="The file metadata explicitly points to a generative tool.",
                what_checked="We checked whether the file names a camera, editing app, or AI generation tool.",
                what_found=f"The metadata directly references generative software: {software or make}.",
                why_it_matters="This is one of the strongest metadata signals, because it is a direct trace left in the file itself.",
                caveat="Metadata can be edited, but an explicit AI software trace is still strong evidence unless there is reason to suspect tampering.",
                observations=observations,
                metrics={"exif_count": len(exif)},
                supports=SignalSupport.AI_GENERATED,
            )

        # Standard Camera Logic
        if make or model:
            observations.append(f"Hardware footprint: {make.capitalize() or 'Unknown'} {model.capitalize() or 'Unknown'}")
            
            # Check for realistic physical optics tags
            important_tags = ["FocalLength", "ExposureTime", "ISOSpeedRatings", "FNumber"]
            found_physics_tags = sum(1 for tag in important_tags if tag in exif)
            
            if found_physics_tags >= 2:
                observations.append(f"Physical optics data present ({found_physics_tags}/{len(important_tags)} core tags).")
                supports = SignalSupport.AUTHENTIC
                reliability = 0.6
                summary = "The metadata looks consistent with a real camera image."
                what_found = (
                    f"The file includes camera details and several normal photo-capture tags "
                    f"({found_physics_tags}/{len(important_tags)} important optics fields present)."
                )
                why_it_matters = "That leans toward a real photograph because the file carries a believable camera footprint."
            else:
                observations.append("Camera make/model exists, but the deeper photo-capture tags are thin or incomplete.")
                supports = SignalSupport.INCONCLUSIVE
                reliability = 0.4
                summary = "The metadata shows some camera information, but it is incomplete."
                what_found = "The file names a device, but the supporting camera-capture details are too thin to fully trust."
                why_it_matters = "That gives some support for authenticity, but not enough to rely on by itself."
                
        else:
            observations.append("Metadata exists, but it does not clearly name the capture device.")
            summary = "The file has some metadata, but not enough to identify a clear source."
            what_found = "There is metadata present, but it does not clearly identify a camera or creation tool."
            why_it_matters = "That leaves provenance uncertain rather than clearly real or clearly generated."

        if software and not is_ai_stamped:
            observations.append(f"Post-processing software trace: {software}")

        return EvidenceSignal(
            id=self.id,
            name=self.name,
            category=self.category,
            status=SignalStatus.OK,
            reliability=reliability,
            summary=summary,
            what_checked="We checked the file for camera details, software traces, and other provenance clues.",
            what_found=what_found,
            why_it_matters=why_it_matters,
            caveat="Metadata helps with provenance, but it can be missing, stripped, or manually edited.",
            observations=observations,
            metrics={"exif_count": len(exif)},
            supports=supports,
            notes="Metadata can be manipulated; this signal evaluates structural consistency of the EXIF block.",
        )
