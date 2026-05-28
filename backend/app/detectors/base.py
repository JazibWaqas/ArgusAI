from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from ..models.evidence import EvidenceSignal


class Detector(ABC):
    id: str
    name: str
    category: str

    @abstractmethod
    async def analyze(self, image, context: Dict[str, Any]) -> EvidenceSignal:
        raise NotImplementedError
