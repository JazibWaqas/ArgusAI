from __future__ import annotations

import json
from typing import Any, Dict

from PIL import ExifTags

from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from .base import Detector


_AI_GENERATOR_NAMES = [
    "midjourney", "dall-e", "dalle", "stable diffusion", "stablediffusion", "openai",
    "comfyui", "automatic1111", "adobe firefly", "firefly", "imagen", "gemini", "sora",
    "veo", "ideogram", "flux", "leonardo.ai", "runwayml", "pika", "kling", "stability.ai",
]


class MetadataDetector(Detector):
    id = "metadata_analysis"
    name = "Metadata & Provenance"
    category = "metadata"

    def _scan_provenance(self, data: bytes) -> EvidenceSignal | None:
        """Scan raw file bytes for Content Credentials (C2PA) and AI provenance markers.
        Works even when EXIF is stripped, and on video containers (Sora/Veo/Gemini), which
        embed the standard 'trainedAlgorithmicMedia' source type. Returns a decisive signal
        when AI provenance is found, an authentic-leaning one for camera/creator credentials,
        else None so the normal EXIF logic runs."""
        if not data:
            return None
        sample = data[:524288] + (data[-65536:] if len(data) > 65536 else b"")
        blob = sample.decode("latin-1", "ignore").lower()

        ai_source = "trainedalgorithmicmedia" in blob  # C2PA/IPTC digital source type for AI
        name_hit = next((n for n in _AI_GENERATOR_NAMES if n in blob), None)
        c2pa_present = ("c2pa" in blob) or ("contentcred" in blob) or ("content credentials" in blob)

        if ai_source or name_hit:
            observations = []
            if ai_source:
                observations.append("Content Credentials (C2PA) digital source type is 'trained algorithmic media' — a standardized AI-generated marker.")
            if name_hit:
                observations.append(f"Embedded metadata references a generative tool: {name_hit}.")
            if c2pa_present and not ai_source:
                observations.append("A C2PA / Content Credentials manifest is embedded in the file.")
            return EvidenceSignal(
                id=self.id, name=self.name, category=self.category,
                status=SignalStatus.OK, reliability=0.92,
                summary="The file's embedded provenance marks it as AI-generated.",
                what_checked="We scanned the file's Content Credentials (C2PA) and embedded provenance metadata for AI-generation markers, including the standardized digital-source-type and known generator names.",
                what_found=("The provenance metadata flags this as trained-algorithmic (AI-generated) media." if ai_source else f"The embedded metadata names a generative tool: {name_hit}."),
                why_it_matters="Provenance markers like C2PA are an industry-standard, hard-to-fake trace written by the generator itself. Finding one is among the strongest provenance signals available.",
                caveat="Provenance can be stripped or, rarely, forged. Absence of a marker is not proof of authenticity.",
                observations=observations,
                metrics={"c2pa_present": c2pa_present, "ai_source_type": ai_source, "generator_named": name_hit},
                supports=SignalSupport.AI_GENERATED,
                notes="Content Credentials / embedded AI provenance scan.",
            )

        if c2pa_present:
            return EvidenceSignal(
                id=self.id, name=self.name, category=self.category,
                status=SignalStatus.OK, reliability=0.5,
                summary="The file carries Content Credentials, with no AI-generation marker.",
                what_checked="We scanned the file for a C2PA / Content Credentials manifest and any AI-generation source-type marker.",
                what_found="A Content Credentials (C2PA) manifest is present and does not flag AI generation, which is consistent with camera capture or a credentialed editing workflow.",
                why_it_matters="Signed Content Credentials are increasingly used by cameras and creators to prove provenance, so their presence without an AI marker leans toward an authentic origin.",
                caveat="We only check for the AI source-type here, not the full signature chain, so treat this as supporting rather than conclusive.",
                observations=["A C2PA / Content Credentials manifest is embedded, with no AI digital-source-type marker."],
                metrics={"c2pa_present": True, "ai_source_type": False},
                supports=SignalSupport.AUTHENTIC,
                notes="Content Credentials present without an AI marker.",
            )
        return None

    async def analyze(self, image, context: Dict[str, Any]) -> EvidenceSignal:
        provenance = self._scan_provenance(context.get("image_bytes", b"") or b"")
        if provenance is not None:
            return provenance

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
