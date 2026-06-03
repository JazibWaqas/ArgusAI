from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

import httpx
from PIL import Image

from .config import settings
from .llm import llm_settings


def _redact_secrets(text: str) -> str:
    if not text:
        return text
    out = re.sub(r"([?&])key=([^&\s'\"]+)", r"\1key=<redacted>", text, flags=re.IGNORECASE)
    out = re.sub(r"(?i)(Bearer\s+)([A-Za-z0-9._-]+)", r"\1<redacted>", out)
    out = re.sub(r"(AIza[0-9A-Za-z_-]{30,})", "<redacted>", out)
    return out


class LLMClient:
    def __init__(self) -> None:
        self.last_error: Optional[str] = None
        self.last_provider: Optional[str] = None
        self.last_model: Optional[str] = None
        self.last_fallback_used: bool = False

    def _parse_google_error(self, response: httpx.Response) -> tuple[Optional[str], str]:
        try:
            data = response.json()
        except Exception:
            text = (response.text or "").strip()
            return None, text[:500] if text else f"HTTP {response.status_code}"

        error = data.get("error") if isinstance(data, dict) else None
        if not isinstance(error, dict):
            return None, f"HTTP {response.status_code}"

        message = str(error.get("message") or f"HTTP {response.status_code}")
        details = error.get("details")
        if isinstance(details, list):
            for item in details:
                if isinstance(item, dict) and item.get("reason"):
                    return str(item.get("reason")), message

        status = error.get("status")
        if status:
            return str(status), message
        return None, message

    def _should_rotate_key(self, status_code: int, reason: Optional[str]) -> bool:
        if status_code in (403, 429, 500, 503, 504):
            return True
        return reason in {
            "API_KEY_INVALID",
            "API_KEY_SERVICE_BLOCKED",
            "API_KEY_HTTP_REFERRER_BLOCKED",
            "API_KEY_IP_ADDRESS_BLOCKED",
            "PERMISSION_DENIED",
        }

    def _should_try_fallback(self, status_code: int, message: str) -> bool:
        if status_code == 404:
            return True
        lowered = (message or "").lower()
        return status_code == 400 and (
            "not found for api version" in lowered
            or "not supported for generatecontent" in lowered
            or "not supported" in lowered
        )

    def _is_transient_error(self, message: Optional[str]) -> bool:
        lowered = (message or "").lower()
        return any(
            token in lowered
            for token in (
                "503",
                "429",
                "service unavailable",
                "temporarily unavailable",
                "timeout",
                "timed out",
                "connection reset",
                "connecterror",
                "read timeout",
                "resource exhausted",
                "quota exceeded",
                "rate-limit",
                "rate limit",
                "high demand",
            )
        )

    def _note_success(self, *, provider: str, model: str, fallback_used: bool = False) -> None:
        self.last_provider = provider
        self.last_model = model
        self.last_fallback_used = fallback_used
        self.last_error = None

    def _note_error(self, message: str, *, provider: Optional[str] = None, model: Optional[str] = None) -> None:
        self.last_error = _redact_secrets(message)
        if provider:
            self.last_provider = provider
        if model:
            self.last_model = model

    def _image_mime_type(self, image_bytes: bytes) -> str:
        # Detect audio files
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WAVE":
            return "audio/wav"
        if image_bytes.startswith(b"ID3") or image_bytes.startswith(b"\xff\xfb") or image_bytes.startswith(b"\xff\xf3") or image_bytes.startswith(b"\xff\xf2"):
            return "audio/mp3"
        if image_bytes.startswith(b"fLaC"):
            return "audio/flac"
        if image_bytes.startswith(b"OggS"):
            return "audio/ogg"
        if image_bytes.startswith(b"\x00\x00\x00") and b"ftyp" in image_bytes[:16] and any(
            brand in image_bytes[:32] for brand in (b"m4a", b"M4A", b"m4b", b"M4B")
        ):
            return "audio/mp4"

        if image_bytes.startswith(b'\x00\x00\x00') and b'ftyp' in image_bytes[:16]:
            return "video/mp4"
        if image_bytes.startswith(b'\x1aE\xdf\xa3'):
            return "video/webm"
        if image_bytes[4:8] == b'moov' or image_bytes[4:8] == b'mdat':
            return "video/quicktime"

        try:
            with Image.open(BytesIO(image_bytes)) as image:
                fmt = (image.format or "").upper()
        except Exception:
            return "image/png"

        return {
            "JPEG": "image/jpeg",
            "JPG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
            "GIF": "image/gif",
            "BMP": "image/bmp",
        }.get(fmt, "image/png")


    async def _post_model(
        self,
        client: httpx.AsyncClient,
        model: str,
        headers: dict,
        payload: dict,
        key: str,
    ) -> httpx.Response:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        req_headers = {**headers, "x-goog-api-key": key}
        response = await client.post(url, headers=req_headers, json=payload)
        response.raise_for_status()
        return response

    async def _try_fallback_model(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        payload: dict,
        key: str,
        *,
        key_index: int,
        primary_model: str,
        reason_prefix: str,
    ) -> Optional[httpx.Response]:
        fallback_model = llm_settings.gemini_fallback_model
        if not fallback_model or fallback_model == primary_model:
            return None

        try:
            fallback_response = await self._post_model(client, fallback_model, headers, payload, key)
            self._note_success(provider="gemini", model=fallback_model, fallback_used=True)
            return fallback_response
        except httpx.HTTPStatusError as fallback_exc:
            fallback_reason, fallback_message = self._parse_google_error(fallback_exc.response)
            self._note_error(
                f"{reason_prefix}; Gemini fallback with key #{key_index} failed "
                f"({fallback_reason or f'HTTP {fallback_exc.response.status_code}'}): {fallback_message}",
                provider="gemini",
                model=fallback_model,
            )
            return None
        except Exception as fallback_exc:
            self._note_error(
                f"{reason_prefix}; Gemini fallback with key #{key_index} failed before completion: {fallback_exc}",
                provider="gemini",
                model=fallback_model,
            )
            return None

    async def _post_with_fallback(self, client: httpx.AsyncClient, base_model: str, headers: dict, payload: dict) -> httpx.Response:

        last_exception = None
        for idx, key in enumerate(llm_settings.gemini_api_keys, start=1):
            try:
                response = await self._post_model(client, base_model, headers, payload, key)
                self._note_success(provider="gemini", model=base_model)
                return response
            except httpx.HTTPStatusError as e:
                reason, message = self._parse_google_error(e.response)

                if (
                    self._should_try_fallback(e.response.status_code, message)
                    or self._is_transient_error(message)
                    or e.response.status_code in (429, 500, 503, 504)
                ):
                    fallback_response = await self._try_fallback_model(
                        client,
                        headers,
                        payload,
                        key,
                        key_index=idx,
                        primary_model=base_model,
                        reason_prefix=(
                            f"Gemini primary model {base_model} failed "
                            f"({reason or f'HTTP {e.response.status_code}'}): {message}"
                        ),
                    )
                    if fallback_response is not None:
                        return fallback_response

                if self._should_rotate_key(e.response.status_code, reason):
                    self._note_error(
                        f"Gemini key #{idx} failed ({reason or f'HTTP {e.response.status_code}'}): {message}",
                        provider="gemini",
                        model=base_model,
                    )
                    last_exception = e
                    continue

                self._note_error(
                    f"Gemini request failed ({reason or f'HTTP {e.response.status_code}'}): {message}",
                    provider="gemini",
                    model=base_model,
                )
                raise
            except Exception as exc:
                fallback_response = await self._try_fallback_model(
                    client,
                    headers,
                    payload,
                    key,
                    key_index=idx,
                    primary_model=base_model,
                    reason_prefix=f"Gemini primary model {base_model} failed before completion: {exc}",
                )
                if fallback_response is not None:
                    return fallback_response

                self._note_error(
                    f"Gemini request failed before completion: {exc}",
                    provider="gemini",
                    model=base_model,
                )
                last_exception = exc
                
        if last_exception:
            raise last_exception
        self._note_error("No Gemini API keys are configured or all keys failed.", provider="gemini", model=base_model)
        raise ValueError("No Gemini keys configured or all exhausted.")

    def _extract_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        t = text.strip()
        t = t.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            obj = json.loads(t)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        m = re.search(r"\{[\s\S]*\}", t)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                return None
        return None

    def _extract_url(self, text: str) -> Optional[str]:
        match = re.search(r"https?://[^\s)>\]\"']+", text or "")
        return match.group(0).rstrip(".,;") if match else None

    async def reverse_image_search(
        self,
        image_bytes: bytes,
        user_context: str = "",
    ) -> list[Dict[str, Any]]:
        """
        Reverse search when the user provides a public image URL.

        Most commercial reverse-image APIs cannot inspect arbitrary local bytes
        directly; they need a hosted URL. We keep this honest and fall back to
        text/grounded provenance research when only an uploaded file is present.
        """
        if not settings.serpapi_key:
            return []
        image_url = self._extract_url(user_context)
        if not image_url:
            return []

        params = {
            "engine": "google_lens",
            "url": image_url,
            "api_key": settings.serpapi_key,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get("https://serpapi.com/search.json", params=params)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            self._note_error(f"Reverse image search failed: {exc}", provider="serpapi", model="google_lens")
            return []

        matches = []
        visual_matches = data.get("visual_matches") if isinstance(data, dict) else None
        if isinstance(visual_matches, list):
            for item in visual_matches[:8]:
                if not isinstance(item, dict):
                    continue
                matches.append(
                    {
                        "url": item.get("link") or item.get("source"),
                        "title": item.get("title"),
                        "source": item.get("source"),
                        "date": item.get("date"),
                    }
                )
        if matches:
            self._note_success(provider="serpapi", model="google_lens")
        return [m for m in matches if m.get("url") or m.get("title")]

    async def grounded_osint_research_agent(
        self,
        image_bytes: bytes,
        user_context: str,
        reverse_matches: Optional[list[Dict[str, Any]]] = None,
    ) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        if not llm_settings.gemini_api_key:
            return None

        ctx = (user_context or "").strip()
        mime = self._image_mime_type(image_bytes)
        is_audio = mime.startswith("audio/")
        is_video = mime.startswith("video/")
        doc_type = "audio recording" if is_audio else "image"
        if is_video:
            doc_type = "video clip"
        action_verb = "listen to" if is_audio else "see"
        sensory_verb = "hear" if is_audio else "see"
        inspect_step = (
            "Step 1: Listen to the audio carefully. Identify speaker names, spoken content, accents, or background cues."
            if is_audio else
            "Step 1: Watch the video carefully. Identify who or what is depicted, visible text, locations, events, and whether the footage changes suspiciously across time."
            if is_video else
            "Step 1: Look at the image carefully. Identify who or what is depicted, any text, logos, locations, or events visible."
        )

        prompt = (
            f"You are a forensic investigative journalist. You can {action_verb} the uploaded {doc_type} directly. "
            f"Use Google Search as a tool to determine the provenance and authenticity of what you {sensory_verb} in the {doc_type}. "
            "Treat the user's context as a claim to investigate, not as proof.\n\n"
            f"User-provided context: {ctx or 'No user claim provided.'}\n\n"
            f"{inspect_step}\n"
            f"Step 2: Use Google Search to find when this {doc_type} or the depicted event/claim first appeared online, and whether fact-checkers have investigated it.\n"
            "Step 3: Verify dates and look for contradictions between the claimed context and what sources actually say.\n\n"
            "Return ONLY one JSON object with exactly these keys:\n"
            "- known_deepfake (boolean)\n"
            "- verified_real (boolean)\n"
            "- earliest_web_appearance (object or null): {date, url, source_name, title}. Use null values inside the object if unknown.\n"
            "- fact_check_sources (array): each {outlet, verdict, url, date}. Include only credible named sources.\n"
            "- timeline_contradiction (object): {present:boolean, explanation:string}\n"
            "- context (string): 4-6 plain sentences naming sources and dates. No generic hedging. If unresolved, say exactly what was missing.\n"
            "- research_hops (integer): number of distinct search rounds or reasoning hops conducted, 1 to 3.\n"
            "- search_queries (array of strings): the main queries used or inferred from grounding metadata.\n"
            "Do not use markdown fences."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": self._image_mime_type(image_bytes),
                                "data": base64.b64encode(image_bytes).decode("utf-8"),
                            }
                        },
                    ]
                }
            ],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.15},
        }
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                response = await self._post_with_fallback(client, llm_settings.gemini_grounding_model, headers, payload)
                data = response.json()
            except Exception:
                return None

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return None
        parsed = self._extract_json_object(text)
        if not parsed:
            self._note_error("Grounded OSINT research agent response was not valid JSON.", provider="gemini", model=llm_settings.gemini_grounding_model)
            return None

        cand0 = data["candidates"][0]
        meta = cand0.get("groundingMetadata") or cand0.get("grounding_metadata") or {}
        if isinstance(meta, dict):
            meta_queries = meta.get("webSearchQueries") or meta.get("web_search_queries") or []
            if meta_queries and not parsed.get("search_queries"):
                parsed["search_queries"] = meta_queries

        try:
            research_hops = int(parsed.get("research_hops") or 1)
        except Exception:
            research_hops = 1

        out = {
            "known_deepfake": bool(parsed.get("known_deepfake")),
            "verified_real": bool(parsed.get("verified_real")),
            "earliest_web_appearance": parsed.get("earliest_web_appearance"),
            "fact_check_sources": parsed.get("fact_check_sources") if isinstance(parsed.get("fact_check_sources"), list) else [],
            "timeline_contradiction": parsed.get("timeline_contradiction") if isinstance(parsed.get("timeline_contradiction"), dict) else {"present": False, "explanation": ""},
            "context": str(parsed.get("context") or "").strip(),
            "research_hops": max(1, min(3, research_hops)),
            "search_queries": parsed.get("search_queries") if isinstance(parsed.get("search_queries"), list) else [],
            "reverse_image_matches": reverse_matches or [],
            "grounded_text": text.strip(),
        }
        return out, meta if isinstance(meta, dict) else {}

    async def grounded_osint_investigation(
        self,
        image_bytes: bytes,
        user_context: str,
    ) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        if not llm_settings.gemini_api_key:
            return None

        ctx = (user_context or "").strip()
        mime = self._image_mime_type(image_bytes)
        is_audio = mime.startswith("audio/")
        is_video = mime.startswith("video/")
        doc_type = "audio recording" if is_audio else "video clip" if is_video else "image"
        if is_audio:
            examine_phrase = "Listen to the audio recording. Use search to determine whether this recording aligns"
        elif is_video:
            examine_phrase = "Watch the video clip. Use search to determine whether this footage aligns"
        else:
            examine_phrase = "Examine the image. Use search to determine whether this image aligns"
        extra = (
            f"\n\nUser-provided context (treat as investigative hints, not proof): {ctx}"
            if ctx
            else ""
        )
        prompt = (
            f"You are a lead forensic journalist with access to Google Search. "
            f"{examine_phrase} with verified real-world reporting "
            f"or is widely described as fabricated, AI-generated, or a known deepfake."
            + extra
            + f"\n\nAfter searching, respond with ONLY a single JSON object (no markdown fences) using exactly these keys:\n"
            "- known_deepfake (boolean): true only if credible reporting or fact-checkers say this depiction is fake, AI, or misleading.\n"
            "- verified_real (boolean): true only if credible outlets corroborate the depicted situation as real.\n"
            f"- context (string): 3-5 plain sentences explaining what you found, what sources said, and why that leads to your verdict. Be specific - name the fact-checkers or outlets if you found them. Write simply, no em dashes, no pretentious phrases.\n"
            f"If the scene/audio is generic with no identifiable public story, set both booleans false and explain in context."
        )


        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": self._image_mime_type(image_bytes),
                                "data": base64.b64encode(image_bytes).decode("utf-8"),
                            }
                        },
                    ]
                }
            ],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.2},
        }
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            for attempt in range(2):
                try:
                    response = await self._post_with_fallback(
                        client,
                        llm_settings.gemini_grounding_model,
                        headers,
                        payload,
                    )
                    data = response.json()
                    break
                except Exception:
                    detail = self.last_error or f"Grounded OSINT request failed via Gemini model {llm_settings.gemini_grounding_model}."
                    self._note_error(
                        detail,
                        provider="gemini",
                        model=self.last_model or llm_settings.gemini_grounding_model,
                    )
                    if attempt == 0 and self._is_transient_error(detail):
                        continue
                    return None

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return None

        cand0 = data["candidates"][0]
        meta = cand0.get("groundingMetadata") or cand0.get("grounding_metadata") or {}
        parsed = self._extract_json_object(text)
        if not parsed:
            self._note_error(
                "Grounded OSINT response could not be parsed as the expected JSON object.",
                provider="gemini",
                model=llm_settings.gemini_grounding_model,
            )
            return None
        out = {
            "known_deepfake": bool(parsed.get("known_deepfake")),
            "verified_real": bool(parsed.get("verified_real")),
            "context": str(parsed.get("context") or "").strip(),
            "grounded_text": text.strip(),
        }
        meta_out = meta if isinstance(meta, dict) else {}
        return out, meta_out

    async def followup_answer(
        self,
        user_message: str,
        verdict: str,
        evidence: Dict[str, Any],
    ) -> Optional[str]:
        system = (
            "You are ArgusAI, a forensic assistant. The user already received a structured analysis. "
            "Answer follow-up questions only using the provided evidence JSON and verdict. "
            "If the question cannot be answered from that evidence, say so clearly. "
            "Be conversational, concise (2-6 sentences), and avoid inventing new forensic claims."
        )
        user = f"Verdict: {verdict}\n\nEvidence JSON:\n{json.dumps(evidence, indent=2)}\n\nUser question:\n{user_message}"

        async def gemini_reply() -> Optional[str]:
            if not llm_settings.gemini_api_key:
                return None
            payload = {
                "contents": [{"parts": [{"text": system + "\n\n" + user}]}],
                "generationConfig": {"temperature": 0.2},
            }
            headers = {"Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=45.0) as client:
                try:
                    response = await self._post_with_fallback(client, llm_settings.gemini_model, headers, payload)
                    data = response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except Exception as exc:
                    detail = self.last_error or str(exc)
                    self._note_error(
                        f"Gemini follow-up request failed: {detail}",
                        provider="gemini",
                        model=self.last_model or llm_settings.gemini_model,
                    )
                    return None

        return await gemini_reply()

    async def focused_media_review(
        self,
        media_bytes: bytes,
        question: str,
        *,
        user_context: str = "",
    ) -> Optional[Dict[str, Any]]:
        if not llm_settings.gemini_api_key or not media_bytes:
            return None

        mime = self._image_mime_type(media_bytes)
        if mime.startswith("audio/"):
            action = "Listen to the submitted audio recording"
            media_word = "audio"
        elif mime.startswith("video/"):
            action = "Watch the submitted video clip"
            media_word = "video"
        else:
            action = "Look closely at the submitted image"
            media_word = "image"

        prompt = (
            "You are ArgusAI's investigator agent. "
            f"{action} and answer the user's focused forensic question. "
            "Do not rerun the full pipeline. Inspect only what is visible or audible in the media. "
            "Separate observations from conclusions. Use plain professional language, no markdown, no em dashes.\n\n"
            f"Original user context: {(user_context or '').strip() or 'None supplied.'}\n"
            f"Focused question: {question.strip()}\n\n"
            "Return only one JSON object with exactly these keys: "
            "answer (string, 2 to 5 sentences), observations (array of strings), confidence (float 0 to 1), media_type (string)."
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime,
                                "data": base64.b64encode(media_bytes).decode("utf-8"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.15},
        }
        headers = {"Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=max(30.0, float(llm_settings.vision_timeout_seconds))) as client:
            try:
                response = await self._post_with_fallback(client, llm_settings.gemini_vision_model, headers, payload)
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as exc:
                detail = self.last_error or str(exc)
                self._note_error(
                    f"Focused media review failed: {detail}",
                    provider="gemini",
                    model=self.last_model or llm_settings.gemini_vision_model,
                )
                return None
        parsed = self._extract_json_object(text) or {"answer": text}
        parsed["media_type"] = str(parsed.get("media_type") or media_word)
        if not isinstance(parsed.get("observations"), list):
            parsed["observations"] = []
        return parsed

    async def investigator_agent_reply(
        self,
        *,
        user_message: str,
        verdict: str,
        report: Dict[str, Any],
        history: list[Dict[str, Any]],
        tools: list[Dict[str, Any]],
        tool_runner: Any,
        max_rounds: int = 3,
    ) -> Optional[Dict[str, Any]]:
        if not llm_settings.gemini_api_key:
            return None

        system = (
            "You are ArgusAI's user-facing Investigator Agent for a completed media forensic report. "
            "You may use tools to inspect the original media, query prior case history, explain detector influence, "
            "run live provenance research, draft a fact-check note, or flag the case for human review. "
            "Use tools when they materially improve the answer. Do not rerun the full forensic pipeline. "
            "Keep tool use bounded. If a tool fails, continue from the report evidence. "
            "Final answers must be clear, professional, concise, and free of filler. Do not use em dashes."
        )
        report_brief = {
            "verdict": verdict,
            "media_type": report.get("media_type"),
            "certainty": report.get("certainty"),
            "confidence_label": report.get("confidence_label"),
            "short_summary": report.get("short_summary"),
            "pipeline_health": report.get("pipeline_health"),
            "phoenix_trace_id": report.get("phoenix_trace_id"),
            "evidence": report.get("evidence") or {"signals": report.get("signals") or []},
            "audio_signal": report.get("signal"),
        }
        prior = [
            {"role": row.get("role"), "content": row.get("content")}
            for row in (history or [])[-8:]
            if row.get("role") in {"user", "assistant"} and row.get("content")
        ]
        contents: list[dict[str, Any]] = [
            {"role": "user", "parts": [{"text": system}]},
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"Current report JSON:\n{json.dumps(report_brief, ensure_ascii=False)[:18000]}\n\n"
                            f"Recent transcript JSON:\n{json.dumps(prior, ensure_ascii=False)[:6000]}\n\n"
                            f"User question: {user_message}"
                        )
                    }
                ],
            },
        ]
        payload_tools = [{"functionDeclarations": tools}]
        headers = {"Content-Type": "application/json"}
        tool_calls: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=45.0) as client:
            for _ in range(max(1, min(max_rounds, 4))):
                payload = {
                    "contents": contents,
                    "tools": payload_tools,
                    "generationConfig": {"temperature": 0.2},
                }
                try:
                    response = await self._post_with_fallback(client, llm_settings.gemini_model, headers, payload)
                    data = response.json()
                    model_content = data["candidates"][0]["content"]
                    parts = model_content.get("parts") or []
                except Exception as exc:
                    detail = self.last_error or str(exc)
                    self._note_error(
                        f"Investigator agent request failed: {detail}",
                        provider="gemini",
                        model=self.last_model or llm_settings.gemini_model,
                    )
                    return None

                function_part = next((p for p in parts if isinstance(p.get("functionCall"), dict)), None)
                if not function_part:
                    text = "\n".join(str(p.get("text") or "").strip() for p in parts if p.get("text")).strip()
                    return {"reply": text, "tool_calls": tool_calls}

                function_call = function_part["functionCall"]
                name = str(function_call.get("name") or "")
                args = function_call.get("args") if isinstance(function_call.get("args"), dict) else {}
                result = await tool_runner(name, args)
                tool_calls.append(
                    {
                        "name": name,
                        "label": result.get("label") or name.replace("_", " "),
                        "ok": bool(result.get("ok", True)),
                    }
                )
                contents.append(model_content)
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": name,
                                    "response": result,
                                }
                            }
                        ],
                    }
                )

        final_prompt = (
            "Tool limit reached. Answer the user's question from the report and tool results already provided. "
            "Be concise and professional."
        )
        contents.append({"role": "user", "parts": [{"text": final_prompt}]})
        payload = {"contents": contents, "generationConfig": {"temperature": 0.2}}
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await self._post_with_fallback(client, llm_settings.gemini_model, headers, payload)
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return {"reply": text, "tool_calls": tool_calls}
            except Exception:
                return {"reply": None, "tool_calls": tool_calls}

    async def generate_explanation(
        self,
        verdict: str,
        evidence: Dict[str, Any],
        reasoning_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if llm_settings.explanation_provider == "gemini" and llm_settings.gemini_api_key:
            return await self._gemini_text_explanation(verdict, evidence, reasoning_summary)
        return None

    async def analyze_image_semantics(self, image_bytes: bytes, user_context: str = "") -> Optional[Dict[str, Any]]:
        if not llm_settings.gemini_api_key:
            return None

        mime = self._image_mime_type(image_bytes)
        is_audio = mime.startswith("audio/")
        is_video = mime.startswith("video/")
        ctx = (user_context or "").strip()
        context_line = (
            f"\nUser-provided context, treat this as a claim to verify rather than proof: {ctx}\n"
            if ctx
            else "\nNo user-provided context was supplied.\n"
        )
        if is_audio:
            prompt = (
                "You are examining this audio recording to decide whether it is authentic human speech or generated/synthesised by AI.\n\n"
                + context_line +
                "Look/listen carefully for specific characteristics that AI voice generators commonly produce:\n"
                "1. Cadence and flow: is the speech rate completely constant, or does it have natural variations and pauses? Describe any robotic transitions.\n"
                "2. Pronunciation and phoneme errors: does the generator mispronounce common words or slur syllables unnaturally?\n"
                "3. Breathing and physiological cues: does the speaker take natural breaths in logical places? AI speech often lacks realistic breathing patterns.\n"
                "4. Background consistency: is there a sudden change in background room acoustics, static, or hiss when the speaker starts/stops talking?\n"
                "5. Voice cloning artifacts: are there spectral anomalies, metallic echoes, or phasey voice sounds?\n\n"
                "Also judge the overall production pattern. If the recording sounds like polished text-to-speech, synthetic narration, cloned voice output, or a Gemini-style generated audio sample, say so directly and raise confidence.\n\n"
                "Respond ONLY with a valid JSON object using exactly these keys:\n"
                "- anomalies (array of strings: each one should describe one specific audio problem you found, naming the timestamp or context and what is wrong with it.)\n"
                "- confidence (float 0.0 to 1.0: how strongly do these specific issues point to AI generation, not just low quality or background noise)\n"
                "- summary (string: 2 to 3 plain sentences describing exactly what you found and why it points toward real or AI.)\n"
                "If you find no issues, anomalies must be an empty array []. Do not include markdown formatting."
            )
        elif is_video:
            prompt = (
                "You are examining this video footage to decide whether it is an authentic recording or generated/manipulated by AI.\n\n"
                + context_line +
                "Look carefully for problems that only become visible across time:\n"
                "1. Temporal consistency: do faces, hands, objects, text, or background details morph, flicker, or shift between frames?\n"
                "2. Physics and motion: do objects move with plausible momentum, contact, shadows, and reflections across the clip?\n"
                "3. Identity consistency: do facial features, clothing details, logos, or scene geometry remain stable?\n"
                "4. Compression versus generation: do not confuse normal video compression, motion blur, or low bitrate artifacts with impossible temporal changes.\n"
                "5. Watermarks: look for visible AI-generation labels or watermarks. If present, confidence must be 1.0.\n\n"
                "Also judge the overall visual production pattern. If the clip has the synthetic style, overly smooth motion, staged surrealism, generated-camera movement, or prompt-like composition typical of Gemini/Imagen/Veo-style AI video, say so directly. You do not need a single frame-level glitch if the full clip is plainly generated.\n\n"
                "Respond ONLY with a valid JSON object using exactly these keys:\n"
                "- anomalies (array of strings: each one should describe one specific temporal or visual problem, naming the moment/location in the footage and what is wrong.)\n"
                "- confidence (float 0.0 to 1.0: how strongly these specific issues point to AI generation, not just low-quality video)\n"
                "- summary (string: 2 to 3 plain sentences describing exactly what you found and why it points toward real footage or AI.)\n"
                "If you find no issues, anomalies must be an empty array []. Do not include markdown formatting."
            )
        else:
            prompt = (
                "You are examining this image to decide whether it was taken by a real camera or generated by AI.\n\n"
                + context_line +
                "Look carefully for specific physical problems that AI generators commonly produce:\n"
                "1. Hands and fingers: count them. Are any fingers fused together, unnaturally elongated, or are there too many? Describe exactly which hand and what is wrong.\n"
                "2. Background geometry: do straight lines stay straight? Do fences, roads, text, or building edges warp or dissolve into each other?\n"
                "3. Text and logos: is any text in the image readable? AI often produces text that looks like letters but is actually gibberish on close inspection.\n"
                "4. Lighting and shadows: does every object cast a shadow that matches the apparent light source? Name any specific objects that cast no shadow or the wrong shadow.\n"
                "5. Watermarks: look at all four corners right now. Is there a Google Gemini sparkle, a colored OpenAI/DALL-E bar, or any text saying 'AI Generated'? If yes, confidence must be 1.0.\n"
                "6. Skin and material texture: is skin unnaturally smooth with no pores? Do fabrics or surfaces look artificially perfect?\n\n"
                "Important: do not flag normal photography choices like intentional blur, filters, retouching, or HDR. Only flag things that would be physically impossible in a real photograph.\n\n"
                "Respond ONLY with a valid JSON object using exactly these keys:\n"
                "- anomalies (array of strings: each one should describe one specific problem you found, naming the exact location in the image and what is wrong with it. Be concrete, not generic.)\n"
                "- confidence (float 0.0 to 1.0: how strongly do these specific issues point to AI generation, not just editing or style)\n"
                "- summary (string: 2 to 3 plain sentences describing exactly what you found and why it points toward real or AI. Be specific. Name the things you saw. Do not use jargon or pretentious language.)\n"
                "If you find no issues, anomalies must be an empty array []. Do not include markdown formatting."
            )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": self._image_mime_type(image_bytes),
                                "data": base64.b64encode(image_bytes).decode("utf-8"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.2}
        }

        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=llm_settings.vision_timeout_seconds) as client:
            for attempt in range(2):
                try:
                    response = await self._post_with_fallback(client, llm_settings.gemini_vision_model, headers, payload)
                    data = response.json()
                    break
                except Exception as exc:
                    detail = self.last_error or str(exc)
                    self._note_error(
                        f"Gemini semantic vision request failed: {detail}",
                        provider="gemini",
                        model=self.last_model or llm_settings.gemini_vision_model,
                    )
                    if attempt == 0 and self._is_transient_error(detail):
                        continue
                    return None

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return {"raw_text": text}
        except (KeyError, IndexError, TypeError):
            self._note_error(
                "Gemini semantic vision response was missing the expected text candidate.",
                provider="gemini",
                model=llm_settings.gemini_vision_model,
            )
            return None

    async def generate_osint_search_queries(
        self, image_bytes: bytes, user_context: str = ""
    ) -> Optional[list[str]]:
        if not llm_settings.gemini_api_key:
            return None

        uc = (user_context or "").strip()
        hint = (
            f"\n\nThe user added this context (use it to sharpen queries): {uc}\n"
            if uc
            else ""
        )
        mime = self._image_mime_type(image_bytes)
        is_audio = mime.startswith("audio/")
        if is_audio:
            prompt = (
                "You are an elite investigative journalist and digital forensics expert. Listen to this audio recording carefully. "
                + hint
                + "If it depicts a generic/unidentifiable speaker or generic stock audio with no specific claim/geopolitical topic, reply strictly with: [\"GENERIC_SCENE\"]\n\n"
                "If it features recognizable public figures, politicians, specific geopolitical claims, or highly specific contexts, "
                "write exactly 3 highly targeted Google search queries to investigate the authenticity of this speech. Your angles should be:\n"
                "1. A direct search for the specific speech/claims or statements made by the depicted public figure.\n"
                "2. A search specifically looking for 'debunk', 'fake audio', 'cloned voice', 'deepfake', or 'fact check' regarding the statements.\n"
                "3. A broader context search to verify if/when the figure made such statements publicly.\n\n"
                "Return ONLY a valid JSON array of strings. Do NOT use markdown. Example:\n"
                "[\"Donald Trump speech speech_text exactly what happened\", \"Donald Trump audio fake voice deepfake fact check\", \"Donald Trump statements regarding speech_topic\"]"
            )
        else:
            prompt = (
                "You are an elite investigative journalist and digital forensics expert. Examine this image carefully. "
                + hint
                + "If it depicts a generic scene (unidentifiable people, random landscape, generic stock photo), reply strictly with: [\"GENERIC_SCENE\"]\n\n"
                "If it depicts recognizable public figures, politicians, specific geopolitical events, viral moments, or highly specific contexts, "
                "write exactly 3 highly targeted Google search queries to investigate the authenticity of this event. Your angles should be:\n"
                "1. A direct chronological news search for the specific event depicted.\n"
                "2. A search specifically looking for 'debunk', 'fake', 'AI generated', or 'fact check' regarding the context.\n"
                "3. A broader entity/location context search to verify if such an event was physically possible or reported.\n\n"
                "Return ONLY a valid JSON array of strings. Do NOT use markdown. Example:\n"
                "[\"Donald Trump arrest New York exactly what happened\", \"Donald Trump arrested fake AI generated fact check\", \"NYPD statements Donald Trump arrest photos\"]"
            )
        payload = {
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": self._image_mime_type(image_bytes), "data": base64.b64encode(image_bytes).decode("utf-8")}}]}]
        }
        async with httpx.AsyncClient(timeout=20) as client:
            for attempt in range(2):
                try:
                    response = await self._post_with_fallback(
                        client, llm_settings.gemini_vision_model, {"Content-Type": "application/json"}, payload
                    )
                    data = response.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                    queries = json.loads(text)
                    if isinstance(queries, list) and len(queries) > 0:
                        return queries
                    self._note_error(
                        "OSINT query generation returned an empty or invalid query list.",
                        provider="gemini",
                        model=llm_settings.gemini_vision_model,
                    )
                    return None
                except Exception as exc:
                    detail = self.last_error or str(exc)
                    self._note_error(
                        f"OSINT query generation failed: {detail}",
                        provider="gemini",
                        model=self.last_model or llm_settings.gemini_vision_model,
                    )
                    if attempt == 0 and self._is_transient_error(detail):
                        continue
                    return None

    async def evaluate_osint_context(self, image_bytes: bytes, search_results: str) -> Optional[Dict[str, Any]]:
        if not llm_settings.gemini_api_key:
            return None
            
        prompt = (
            "You are a Lead Forensic Journalist. I am providing you with an image and a massive dump of live Web Search Results pulled from multiple investigative queries.\n\n"
            f"LIVE WEB RESULTS:\n{search_results}\n\n"
            "Compare the image strictly against this aggregate news intel. Does the open internet explicitly trace this to a verified real event covered by credible reporters? "
            "Or do the news results explicitly warn that this specific image/event is a known viral AI Deepfake/Fabrication?\n\n"
            "You must synthesize the articles carefully. Many fake images have articles written about them *saying* they are fake.\n\n"
            "Return ONLY valid JSON with keys:\n"
            "- known_deepfake (boolean: true if news consensus confirms it is fabricated)\n"
            "- verified_real (boolean: true if credible news confirms the event actually happened physically)\n"
            "- context (string: 3-4 plain sentences explaining what the web found and why it leads to your conclusion. Say which specific sources or fact-checkers flagged it if present. Write simply and clearly, like explaining to someone who has no journalism background. No em dashes, no pretentious language.)\n"
            "Do not use markdown formatting like ```json."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": self._image_mime_type(image_bytes), "data": base64.b64encode(image_bytes).decode("utf-8")}}]}]
        }
        async with httpx.AsyncClient(timeout=20) as client:
            for attempt in range(2):
                try:
                    response = await self._post_with_fallback(
                        client, llm_settings.gemini_vision_model, {"Content-Type": "application/json"}, payload
                    )
                    data = response.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                    return json.loads(text)
                except Exception as exc:
                    detail = self.last_error or str(exc)
                    self._note_error(
                        f"OSINT evidence synthesis failed: {detail}",
                        provider="gemini",
                        model=self.last_model or llm_settings.gemini_vision_model,
                    )
                    if attempt == 0 and self._is_transient_error(detail):
                        continue
                    return None

    def _get_reasoner_system_prompt(self, media_type: str = "image") -> str:
        if media_type == "video":
            report_type = "video verification report"
            evidence_item = "footage"
            concrete = "frames, motion artifacts, temporal inconsistencies, named anomalies, specific visual errors"
        elif media_type == "audio":
            report_type = "audio authenticity report"
            evidence_item = "recording"
            concrete = "voice probabilities, cadence findings, acoustic artifacts, speaker/context findings"
        else:
            report_type = "image verification report"
            evidence_item = "image"
            concrete = "actual numbers, named anomalies, specific anatomy errors"
        return (
            f"You are writing the explanation section of a {report_type} for a general audience."
            " The reader has no technical background. Your job is to explain, in plain language, exactly what the system found"
            " and how it reached its conclusion. Think of it as explaining your reasoning to a curious friend, not writing a lab report.\n\n"
            "STRUCTURE: Write exactly three short paragraphs. No bullet points, no headers, no markdown.\n"
            "- Paragraph 1: State the verdict and confidence directly. Tell the reader what the bottom line is and how sure the system is."
            " Mention how many checks ran and how they split (e.g. two pointed toward AI, one toward real, three were inconclusive).\n"
            "- Paragraph 2: Walk through the two or three most important findings. For each one, say what the check actually did,"
            f" what it specifically found in this {evidence_item}, and why that points toward real or AI. Use the specific details from the evidence data"
            f" ({concrete}, etc.). Do not just repeat the check name. Mention the strongest counter-evidence too.\n"
            "- Paragraph 3: Be honest about what the system could not settle. Say which checks were inconclusive and why, and remind the"
            " reader that no single check is definitive on its own.\n\n"
            "STYLE RULES:\n"
            "- Write like you are explaining something to a smart person who is not a technical expert. Clear, honest, direct.\n"
            "- No em dashes. Use commas or short sentences instead.\n"
            "- No AI-sounding filler phrases: no 'it is worth noting', 'it is important to consider', 'in conclusion', 'forensic analysis reveals', 'it should be noted'.\n"
            "- Use first person plural naturally: 'we found', 'the scan showed', 'we looked at', 'that means'.\n"
            "- Keep it specific. If the spectral model scored 94% AI, say that number. If the visual check found six fingers, say six fingers.\n"
            "- Each paragraph: 3 to 5 sentences. The whole explanation should take under 45 seconds to read.\n"
            "- Never invent findings. Only describe what is in the evidence data provided."
        )

    async def _gemini_text_explanation(
        self,
        verdict: str,
        evidence: Dict[str, Any],
        reasoning_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        summary_json = json.dumps(reasoning_summary or {}, indent=2)
        media_type = str(evidence.get("media_type") or (reasoning_summary or {}).get("media_type") or "image")
        prompt = (
            f"{self._get_reasoner_system_prompt(media_type)}\n\n"
            f"Verdict Declared: {verdict}\n\n"
            f"Reasoning Summary:\n{summary_json}\n\n"
            f"Evidence JSON Profile:\n{json.dumps(evidence, indent=2)}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3}
        }
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await self._post_with_fallback(client, llm_settings.explanation_model, headers, payload)
                data = response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as exc:
                detail = self.last_error or str(exc)
                self._note_error(
                    f"Gemini explanation request failed: {detail}",
                    provider="gemini",
                    model=self.last_model or llm_settings.explanation_model,
                )
                return None
