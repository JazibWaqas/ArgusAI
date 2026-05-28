from __future__ import annotations

from typing import List

from .base import Detector


class DetectorRegistry:
    def __init__(self) -> None:
        self._detectors: List[Detector] = []

    def register(self, detector: Detector) -> None:
        self._detectors = [item for item in self._detectors if item.id != detector.id]
        self._detectors.append(detector)

    def all(self) -> List[Detector]:
        return list(self._detectors)


registry = DetectorRegistry()
