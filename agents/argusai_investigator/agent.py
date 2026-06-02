from __future__ import annotations

import os
import shutil

from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from mcp import StdioServerParameters

from .tools import (
    analyze_media,
    detect_accuracy_drift,
    draft_fact_check_note,
    flag_for_human_review,
    get_arize_health,
    get_detector_reliability,
    get_recent_argusai_traces,
    get_similar_past_cases,
    recalibrate_detector_weight,
)

load_dotenv()


def _first_gemini_key() -> str | None:
    if os.getenv("GOOGLE_API_KEY"):
        return os.getenv("GOOGLE_API_KEY")
    values: list[str] = []
    for key in ("GEMINI_API_KEY", "GEMINI_API_KEYS"):
        raw = os.getenv(key) or ""
        for part in raw.replace("\r", "\n").replace(";", "\n").replace(",", "\n").split("\n"):
            val = part.strip().strip('"').strip("'")
            if val:
                values.append(val)
    return values[0] if values else None


first_key = _first_gemini_key()
if first_key:
    os.environ.setdefault("GOOGLE_API_KEY", first_key)


def _phoenix_mcp_toolset() -> MCPToolset:
    base_url = (os.getenv("PHOENIX_DASHBOARD_URL") or "http://localhost:6006").rstrip("/")
    api_key = (os.getenv("PHOENIX_API_KEY") or "").strip()
    npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    args = ["-y", "@arizeai/phoenix-mcp@latest", "--baseUrl", base_url]
    if api_key:
        args.extend(["--apiKey", api_key])
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(command=npx, args=args),
            timeout=30.0,
        ),
        tool_name_prefix="phoenix",
    )


INSTRUCTION = """
You are ArgusAI Investigator, a forensic media investigation agent.

Core framing: forensic investigation platform, not classifier. Evidence trail, not score.

Your job is to plan and execute an investigation using tools. Do not merely chat.
For a media authenticity goal, choose steps based on evidence:
1. Run ArgusAI analysis when a local file path is provided.
2. Check Phoenix/Arize health and recent traces so the audit trail is visible.
3. Query detector reliability and similar past cases when a detector matters.
4. If detector reliability has drifted, call detect_accuracy_drift and, when justified,
   call recalibrate_detector_weight with a bounded multiplier and a clear reason.
5. If public provenance or a claim matters, use the analysis OSINT summary and draft a
   fact-check note.
6. If evidence is weak or conflicting, flag for human review instead of overclaiming.

You may use Phoenix MCP tools to inspect traces/spans/latency. Mention when you used
Phoenix as the audit layer. Use Firestore-backed reliability from ArgusAI tools for
running intelligence. Keep answers concise, professional, and demo-ready.

Never claim legal certainty. Say when evidence is inconclusive. When you recalibrate a
detector, explicitly state the multiplier, detector id, and why the change is bounded.
"""


root_agent = Agent(
    name="argusai_investigator",
    model=os.getenv("ADK_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.5-flash")),
    description="ArgusAI forensic investigator and self-governing reliability agent.",
    instruction=INSTRUCTION,
    tools=[
        analyze_media,
        get_arize_health,
        get_recent_argusai_traces,
        get_detector_reliability,
        detect_accuracy_drift,
        get_similar_past_cases,
        recalibrate_detector_weight,
        draft_fact_check_note,
        flag_for_human_review,
        _phoenix_mcp_toolset(),
    ],
)
