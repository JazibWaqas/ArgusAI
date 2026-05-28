from __future__ import annotations

import asyncio
from typing import Any, Dict

try:
    from ddgs import DDGS
except Exception:
    DDGS = None  # type: ignore[assignment]

from ..core.llm import llm_settings
from ..core.llm_client import LLMClient
from ..models.evidence import EvidenceSignal, SignalStatus, SignalSupport
from .base import Detector


class OpenSourceIntelligenceDetector(Detector):
    id = "osint_verification"
    name = "Live Web Fact-Checking (OSINT)"
    category = "forensic"

    async def analyze(self, image, context: Dict[str, Any]) -> EvidenceSignal:
        image_bytes: bytes = context.get("image_bytes", b"")
        user_context: str = str(context.get("user_context") or "").strip()

        if not image_bytes:
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.UNAVAILABLE,
                reliability=0.0,
                summary="This web verification check could not run because the raw image bytes were missing.",
                what_checked="We try to find whether the image or the event it claims to show appears in trustworthy public reporting.",
                what_found="The OSINT detector did not receive the image data it needed.",
                why_it_matters="Context can help confirm whether an image matches a real public event or a known fake.",
                caveat="This is a detector issue, not evidence about the image.",
                observations=["Requires raw image bytes."],
                supports=SignalSupport.UNKNOWN,
            )

        if not user_context:
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.UNAVAILABLE,
                reliability=0.0,
                summary="Web verification was skipped. Add context to enable it.",
                what_checked="We search the web to see whether the image or the event it shows has been verified or debunked publicly.",
                what_found="No context was provided, so the web search was not run.",
                why_it_matters="OSINT works best when you give it a clue, for example 'Is this a real photo of the Gaza ceasefire?' Without that, there is nothing specific to search for.",
                caveat="Add a description or claim in the context box and re-run to activate this check.",
                observations=["OSINT skipped: no user context provided."],
                supports=SignalSupport.UNKNOWN,
            )

        client = LLMClient()

        if llm_settings.osint_use_grounding and llm_settings.gemini_api_key:
            # Gemini sees the image directly and uses Google Search to investigate —
            # no separate reverse-image-search API needed.
            research = await client.grounded_osint_research_agent(image_bytes, user_context, [])
            if research:
                fact_check, meta = research
                is_deepfake = fact_check.get("known_deepfake", False)
                is_real = fact_check.get("verified_real", False)
                research_context = fact_check.get("context", "")
                hops = int(fact_check.get("research_hops") or 1)
                earliest = fact_check.get("earliest_web_appearance") or None
                fact_sources = fact_check.get("fact_check_sources") or []
                timeline = fact_check.get("timeline_contradiction") or {"present": False, "explanation": ""}
                queries_used = fact_check.get("search_queries") or []

                observations = [
                    "OSINT mode: Gemini vision + Google Search grounding.",
                    f"Research hops conducted: {hops}",
                ]
                if queries_used:
                    observations.append(f"Search queries used: {len(queries_used)}")
                if earliest:
                    observations.append(f"Earliest appearance candidate: {earliest}")
                if fact_sources:
                    observations.append(
                        "Fact-check sources: "
                        + ", ".join(str(item.get("outlet") or item.get("url") or "source") for item in fact_sources[:5] if isinstance(item, dict))
                    )
                if timeline.get("present"):
                    observations.append(f"Timeline contradiction: {timeline.get('explanation')}")
                if research_context:
                    observations.append(f"Grounded synthesis: {research_context}")

                context_preview = (research_context[:450].rstrip() + ("..." if len(research_context) > 450 else "")) if research_context else ""
                if is_deepfake:
                    summary = "The research agent found credible public sources flagging this image or claim as fabricated."
                    supports = SignalSupport.AI_GENERATED
                    reliability = 0.98
                    why_it_matters = (
                        "Named fact-checks and dated public provenance are stronger than a naked model score because they show where the claim came from "
                        "and whether journalists have already verified or debunked it."
                    )
                elif is_real:
                    summary = "The research agent found credible reporting that corroborates the depicted event or scene."
                    supports = SignalSupport.AUTHENTIC
                    reliability = 0.75
                    why_it_matters = (
                        "Corroborated public reporting supports the underlying event. It still does not prove every pixel is untouched, "
                        "so the image-level detectors remain important."
                    )
                else:
                    summary = "The research agent found related public context but no decisive provenance verdict."
                    supports = SignalSupport.INCONCLUSIVE
                    reliability = 0.45
                    why_it_matters = (
                        "Public context can narrow the investigation, but unresolved provenance should not be over-weighted as proof."
                    )

                metrics: Dict[str, Any] = {
                    "deepfake_flag": is_deepfake,
                    "verified_flag": is_real,
                    "grounding": True,
                    "research_hops": hops,
                    "earliest_web_appearance": earliest,
                    "fact_check_sources": fact_sources,
                    "timeline_contradiction": timeline,
                    "search_queries": queries_used,
                    "provider": client.last_provider,
                    "model": client.last_model,
                    "fallback_used": client.last_fallback_used,
                }
                if isinstance(meta, dict) and meta:
                    metrics["grounding_metadata"] = meta

                return EvidenceSignal(
                    id=self.id,
                    name=self.name,
                    category=self.category,
                    status=SignalStatus.OK,
                    reliability=reliability,
                    summary=summary,
                    what_checked="Gemini visually analyzes the image and uses Google Search grounding to find provenance, fact-checks, original context, and timeline contradictions.",
                    what_found=context_preview or "The research agent completed, but did not return a concise public-source synthesis.",
                    why_it_matters=why_it_matters,
                    caveat="OSINT is strongest for public figures, viral claims, and news events. Generic private images may have no searchable provenance.",
                    observations=observations,
                    metrics=metrics,
                    supports=supports,
                    notes="Gemini vision + Google Search grounding. Gemini sees the image and searches the web — no third-party image search API required.",
                )

            grounded = await client.grounded_osint_investigation(image_bytes, user_context)
            if grounded:
                fact_check, meta = grounded
                is_deepfake = fact_check.get("known_deepfake", False)
                is_real = fact_check.get("verified_real", False)
                grounded_context = fact_check.get("context", "")
                context_preview = (grounded_context[:350].rstrip() + ("..." if len(grounded_context) > 350 else "")) if grounded_context else ""
                queries_used = []
                if isinstance(meta, dict):
                    queries_used = meta.get("webSearchQueries") or meta.get("web_search_queries") or []

                observations = [
                    "OSINT mode: Google Search grounding (Gemini).",
                ]
                if queries_used:
                    observations.append(f"Search queries used: {len(queries_used)}")
                if grounded_context:
                    observations.append(f"Grounded synthesis: {grounded_context}")

                if is_deepfake:
                    summary = "Web fact-checking found this image or claim is publicly flagged as a fabrication."
                    supports = SignalSupport.AI_GENERATED
                    reliability = 0.98
                    what_found = context_preview if context_preview else "Search results and grounded context identify this image or claim as fake, misleading, or AI-generated."
                    why_it_matters = (
                        "When fact-checkers or news organizations have already publicly identified something as fabricated, "
                        "that documented record is one of the strongest signals we have. The deception has already been caught and reported."
                    )
                    observations.append(
                        "Critical: Grounded sources describe this depiction as fabricated, AI-generated, or misleading."
                    )
                elif is_real:
                    summary = "Google-grounded search confirms credible real-world reporting on this event or scene."
                    supports = SignalSupport.AUTHENTIC
                    reliability = 0.7
                    what_found = context_preview if context_preview else "Search results line up with credible reporting about the depicted event or situation."
                    why_it_matters = (
                        "Real-world events documented in credible journalism provide strong contextual support. "
                        "This confirms the underlying scene is real and reported, even if it does not guarantee the specific image is unaltered."
                    )
                    observations.append(
                        "Verified: Extracted context matches credible reporting on the depicted situation."
                    )
                else:
                    summary = "Google grounding found related coverage but no clear fact-checking consensus on this specific image."
                    supports = SignalSupport.INCONCLUSIVE
                    reliability = 0.45
                    what_found = context_preview if context_preview else "The web search found related context, but no clear public determination on this exact image."
                    why_it_matters = (
                        "The subject exists publicly, but the web has not decisively verified or debunked this specific image. "
                        "Context is background information rather than a verdict."
                    )
                    observations.append(
                        "Warning: Subject matter may appear in news, but authenticity of this specific image is not clearly settled in sources."
                    )

                metrics: Dict[str, Any] = {
                    "deepfake_flag": is_deepfake,
                    "verified_flag": is_real,
                    "grounding": True,
                    "provider": client.last_provider,
                    "model": client.last_model,
                    "fallback_used": client.last_fallback_used,
                }
                if isinstance(meta, dict) and meta:
                    metrics["grounding_metadata"] = meta

                return EvidenceSignal(
                    id=self.id,
                    name=self.name,
                    category=self.category,
                    status=SignalStatus.OK,
                    reliability=reliability,
                    summary=summary,
                    what_checked="We searched the web to see whether this image or event is publicly verified, disputed, or debunked.",
                    what_found=what_found,
                    why_it_matters=why_it_matters,
                    caveat="OSINT is best for public claims and known events. It is much less useful for generic scenes with no clear context.",
                    observations=observations,
                    metrics=metrics,
                    supports=supports,
                    notes="Grounded with Google Search via Gemini when available.",
                )

        queries = await client.generate_osint_search_queries(image_bytes, user_context)

        if not queries or "GENERIC_SCENE" in queries:
            observations = ["Zero specific public figures or geopolitical events recognized by OSINT protocol."]
            if client.last_error:
                observations.append(client.last_error)
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.WARNING,
                reliability=0.1,
                summary="The image looks too generic for meaningful web verification.",
                what_checked="We tried to determine whether the scene points to a known public event, person, or widely discussed claim.",
                what_found="The scene does not appear specific enough for a useful web fact-check.",
                why_it_matters="OSINT only helps when there is a public event or claim to verify. Generic scenes usually cannot be confirmed this way.",
                caveat="A skipped OSINT check does not say anything negative about the image. It only means there was no clear public context to search.",
                observations=observations,
                metrics={"provider": client.last_provider, "model": client.last_model, "fallback_used": client.last_fallback_used},
                supports=SignalSupport.UNKNOWN,
            )

        try:
            def sync_search(search_queries):
                if DDGS is None:
                    raise RuntimeError("ddgs package is not installed.")
                pooled_results = []
                seen_urls = set()
                with DDGS() as ddgs:
                    for q in search_queries:
                        results = list(ddgs.text(q, max_results=5))
                        for r in results:
                            url = r.get("href", "")
                            if url not in seen_urls:
                                seen_urls.add(url)
                                pooled_results.append(f"- QUERY [{q}] -> {r.get('title')}: {r.get('body')}")
                return pooled_results

            results_list = await asyncio.to_thread(sync_search, queries)
            if not results_list:
                raise ValueError("Massive investigative sweep returned zero global results.")

            search_str = "\n".join(results_list)

        except Exception as exc:
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.ERROR,
                reliability=0.0,
                summary="This web verification check failed while gathering search results.",
                what_checked="We tried to search the public web for corroboration or debunking of the scene.",
                what_found="The OSINT pipeline could not complete the search step.",
                why_it_matters="This removes one contextual check from the final result.",
                caveat="This is a search failure, not evidence about the image.",
                observations=[f"Error accessing open web: {exc}"],
                metrics={"provider": client.last_provider, "model": client.last_model, "fallback_used": client.last_fallback_used},
                supports=SignalSupport.UNKNOWN,
            )

        fact_check = await client.evaluate_osint_context(image_bytes, search_str)
        if not fact_check:
            observations = ["Queries executed, but the final LLM synthesis was not usable."]
            if client.last_error:
                observations.append(client.last_error)
            return EvidenceSignal(
                id=self.id,
                name=self.name,
                category=self.category,
                status=SignalStatus.ERROR,
                reliability=0.0,
                summary="The web search ran, but the fact-check summary could not be parsed cleanly.",
                what_checked="We searched the web for reporting, fact-checks, and public context tied to the image.",
                what_found="The search completed, but the final synthesis was not usable.",
                why_it_matters="This removes one contextual signal from the final result.",
                caveat="This is a synthesis failure, not evidence about the image.",
                observations=observations,
                metrics={"provider": client.last_provider, "model": client.last_model, "fallback_used": client.last_fallback_used},
                supports=SignalSupport.UNKNOWN,
            )

        is_deepfake = fact_check.get("known_deepfake", False)
        is_real = fact_check.get("verified_real", False)
        context_str = fact_check.get("context", "Context parsed but empty.")

        # Trim context to a readable card length — full version stays in observations
        context_preview = context_str[:350].rstrip() + ("..." if len(context_str) > 350 else "")

        observations = [
            "OSINT mode: DuckDuckGo + LLM synthesis (fallback).",
            f"Investigatory queries executed: {len(queries)}",
            f"Unique articles analyzed: {len(results_list)}",
            f"Fact-Checker Synthesis: {context_str}",
        ]
        if client.last_fallback_used:
            observations.append("Gemini fallback model was used for at least one request.")

        if is_deepfake:
            summary = "Live web fact-checking found this is a known fabrication circulating online."
            supports = SignalSupport.AI_GENERATED
            reliability = 0.98
            what_found = (
                f"Searching {len(results_list)} articles across {len(queries)} investigative queries, the web consensus is clear: "
                f"{context_preview}"
            )
            why_it_matters = (
                "When credible fact-checkers or news organizations have already identified an image as fabricated, "
                "that public record is one of the strongest signals we have — it means the deception has already been caught and documented."
            )
            observations.append(
                "CRITICAL: The open internet explicitly flags this event or image as a fabricated deepfake."
            )
        elif is_real:
            summary = "Multiple independent sources corroborate that this event or scene actually happened."
            supports = SignalSupport.AUTHENTIC
            reliability = 0.7
            what_found = (
                f"Across {len(results_list)} articles from {len(queries)} search angles, coverage consistently supports the depicted event: "
                f"{context_preview}"
            )
            why_it_matters = (
                "Real-world events documented in credible journalism provide strong contextual support for authenticity. "
                "This doesn't guarantee the exact image is unaltered — but it confirms the underlying scene is real and reported."
            )
            observations.append(
                "Verified: Extracted context matches verified real-world reporting and eyewitness accounts."
            )
        else:
            summary = "The event is in the public record, but no clear fact-checking verdict exists for this specific image."
            supports = SignalSupport.INCONCLUSIVE
            reliability = 0.4
            what_found = (
                f"Analyzing {len(results_list)} articles from {len(queries)} angles found related coverage, but no decisive conclusion: "
                f"{context_preview}"
            )
            why_it_matters = (
                "The subject exists publicly, but the web hasn't definitively verified or debunked this specific image. "
                "That leaves context as background information rather than a clear verdict."
            )
            observations.append(
                "Warning: Open web confirms the subject matter, but no explicit fact-checking consensus on this specific image was found."
            )

        return EvidenceSignal(
            id=self.id,
            name=self.name,
            category=self.category,
            status=SignalStatus.OK,
            reliability=reliability,
            summary=summary,
            what_checked="We searched the web to see whether this image or claim has been verified, disputed, or debunked publicly.",
            what_found=what_found,
            why_it_matters=why_it_matters,
            caveat="OSINT is about public context, not just pixel analysis. It is strongest for famous events and weakest for generic scenes.",
            observations=observations,
            metrics={
                "deepfake_flag": is_deepfake,
                "verified_flag": is_real,
                "grounding": False,
                "provider": client.last_provider,
                "model": client.last_model,
                "fallback_used": client.last_fallback_used,
            },
            supports=supports,
        )
