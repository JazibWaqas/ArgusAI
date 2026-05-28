from __future__ import annotations

import os
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


def _gemini_keys_from_dotenv(path: str = ".env") -> List[str]:
    keys: List[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if not line.startswith("GEMINI_API_KEY="):
                    continue
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    keys.append(val)
    except OSError:
        pass
    seen = set()
    out: List[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


class LLMSettings:
    def __init__(self) -> None:
        keys = _gemini_keys_from_dotenv()
        single = os.getenv("GEMINI_API_KEY")
        if not keys and single and single.strip():
            keys = [single.strip().strip('"').strip("'")]
        self.gemini_api_keys = [k for k in keys if k]
        self.gemini_api_key = self.gemini_api_keys[0] if self.gemini_api_keys else None
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        _vision = (os.getenv("GEMINI_VISION_MODEL") or "").strip()
        self.gemini_vision_model = _vision if _vision else self.gemini_model
        _ground = (os.getenv("GEMINI_GROUNDING_MODEL") or "").strip()
        self.gemini_grounding_model = _ground if _ground else self.gemini_model
        self.gemini_fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
        self.osint_use_grounding = os.getenv("OSINT_USE_GROUNDING", "1") == "1"
        
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.explanation_provider = os.getenv("LLM_EXPLANATION_PROVIDER", "groq")
        self.explanation_max_tokens = int(os.getenv("LLM_EXPLANATION_MAX_TOKENS", "900"))
        self.vision_timeout_seconds = float(os.getenv("LLM_VISION_TIMEOUT_SECONDS", "20"))

    def provider_ready(self) -> Optional[str]:
        if self.explanation_provider == "gemini":
            return "gemini" if self.gemini_api_key else None
        if self.explanation_provider == "groq":
            return "groq" if self.groq_api_key else None
        return None

    def health_snapshot(self) -> Dict[str, object]:
        return {
            "gemini_key_count": len(self.gemini_api_keys),
            "gemini_available": bool(self.gemini_api_key),
            "gemini_model": self.gemini_model,
            "gemini_vision_model": self.gemini_vision_model,
            "gemini_grounding_model": self.gemini_grounding_model,
            "gemini_fallback_model": self.gemini_fallback_model,
            "osint_use_grounding": self.osint_use_grounding,
            "groq_available": bool(self.groq_api_key),
            "groq_model": self.groq_model,
            "explanation_provider": self.explanation_provider,
            "provider_ready": self.provider_ready(),
        }


llm_settings = LLMSettings()
