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
                "service unavailable",
                "temporarily unavailable",
                "timeout",
                "timed out",
                "connection reset",
                "connecterror",
                "read timeout",
                "resource exhausted",
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

    async def _post_with_fallback(self, client: httpx.AsyncClient, base_model: str, headers: dict, payload: dict) -> httpx.Response:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{base_model}:generateContent"

        last_exception = None
        for idx, key in enumerate(llm_settings.gemini_api_keys, start=1):
            req_headers = {**headers, "x-goog-api-key": key}
            try:
                response = await client.post(url, headers=req_headers, json=payload)
                response.raise_for_status()
                self._note_success(provider="gemini", model=base_model)
                return response
            except httpx.HTTPStatusError as e:
                reason, message = self._parse_google_error(e.response)

                if self._should_rotate_key(e.response.status_code, reason):
                    self._note_error(
                        f"Gemini key #{idx} failed ({reason or f'HTTP {e.response.status_code}'}): {message}",
                        provider="gemini",
                        model=base_model,
                    )
                    last_exception = e
                    continue

                if self._should_try_fallback(e.response.status_code, message):
                    fallback_model = llm_settings.gemini_fallback_model
                    fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/{fallback_model}:generateContent"
                    try:
                        fallback_response = await client.post(fallback_url, headers=req_headers, json=payload)
                        fallback_response.raise_for_status()
                        self._note_success(provider="gemini", model=fallback_model, fallback_used=True)
                        return fallback_response
                    except httpx.HTTPStatusError as fallback_exc:
                        fallback_reason, fallback_message = self._parse_google_error(fallback_exc.response)
                        if self._should_rotate_key(fallback_exc.response.status_code, fallback_reason):
                            self._note_error(
                                f"Gemini fallback with key #{idx} failed ({fallback_reason or f'HTTP {fallback_exc.response.status_code}'}): {fallback_message}",
                                provider="gemini",
                                model=fallback_model,
                            )
                            last_exception = fallback_exc
                            continue
                        self._note_error(
                            f"Gemini fallback model {fallback_model} failed ({fallback_reason or f'HTTP {fallback_exc.response.status_code}'}): {fallback_message}",
                            provider="gemini",
                            model=fallback_model,
                        )
                        raise fallback_exc

                self._note_error(
                    f"Gemini request failed ({reason or f'HTTP {e.response.status_code}'}): {message}",
                    provider="gemini",
                    model=base_model,
                )
                raise
            except Exception as exc:
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
        prompt = (
            "You are a forensic investigative journalist. You can see the uploaded image directly. "
            "Use Google Search as a tool to determine the provenance and authenticity of what you see in the image. "
            "Treat the user's context as a claim to investigate, not as proof.\n\n"
            f"User-provided context: {ctx or 'No user claim provided.'}\n\n"
            "Step 1: Look at the image carefully. Identify who or what is depicted, any text, logos, locations, or events visible. "
            "Step 2: Use Google Search to find when this image or the depicted event first appeared online, and whether fact-checkers have investigated it. "
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
        extra = (
            f"\n\nUser-provided context (treat as investigative hints, not proof): {ctx}"
            if ctx
            else ""
        )
        prompt = (
            "You are a lead forensic journalist with access to Google Search. "
            "Examine the image. Use search to determine whether this image aligns with verified real-world reporting "
            "or is widely described as fabricated, AI-generated, or a known deepfake."
            + extra
            + "\n\nAfter searching, respond with ONLY a single JSON object (no markdown fences) using exactly these keys:\n"
            "- known_deepfake (boolean): true only if credible reporting or fact-checkers say this depiction is fake, AI, or misleading.\n"
            "- verified_real (boolean): true only if credible outlets corroborate the depicted situation as real.\n"
            "- context (string): 3-5 plain sentences explaining what you found, what sources said, and why that leads to your verdict. Be specific - name the fact-checkers or outlets if you found them. Write simply, no em dashes, no pretentious phrases.\n"
            "If the scene is generic with no identifiable public story, set both booleans false and explain in context."
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

    async def generate_explanation(
        self,
        verdict: str,
        evidence: Dict[str, Any],
        reasoning_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if llm_settings.explanation_provider == "gemini" and llm_settings.gemini_api_key:
            return await self._gemini_text_explanation(verdict, evidence, reasoning_summary)
        return None

    async def analyze_image_semantics(self, image_bytes: bytes) -> Optional[Dict[str, Any]]:
        if not llm_settings.gemini_api_key:
            return None

        prompt = (
            "You are examining this image to decide whether it was taken by a real camera or generated by AI.\n\n"
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

    def _get_reasoner_system_prompt(self) -> str:
        return (
            "You are writing the explanation section of an image verification report for a general audience."
            " The reader has no technical background. Your job is to explain, in plain language, exactly what the system found"
            " and how it reached its conclusion. Think of it as explaining your reasoning to a curious friend, not writing a lab report.\n\n"
            "STRUCTURE: Write exactly three short paragraphs. No bullet points, no headers, no markdown.\n"
            "- Paragraph 1: State the verdict and confidence directly. Tell the reader what the bottom line is and how sure the system is."
            " Mention how many checks ran and how they split (e.g. two pointed toward AI, one toward real, three were inconclusive).\n"
            "- Paragraph 2: Walk through the two or three most important findings. For each one, say what the check actually did,"
            " what it specifically found in this image, and why that points toward real or AI. Use the specific details from the evidence data"
            " (actual numbers, named anomalies, specific anatomy errors, etc.). Do not just repeat the check name. Mention the strongest counter-evidence too.\n"
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
        prompt = (
            f"{self._get_reasoner_system_prompt()}\n\n"
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
                response = await self._post_with_fallback(client, llm_settings.gemini_model, headers, payload)
                data = response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as exc:
                detail = self.last_error or str(exc)
                self._note_error(
                    f"Gemini explanation request failed: {detail}",
                    provider="gemini",
                    model=self.last_model or llm_settings.gemini_model,
                )
                return None
