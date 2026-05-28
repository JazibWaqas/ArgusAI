# AGENTS.md — ArgusAI Working Instructions

Read `CLAUDE.md` first. It is the current hackathon source of truth and explains the product strategy, implementation state, and why the Arize reliability governor is the winning angle.

Critical framing:

- ArgusAI is a forensic investigation platform, not a classifier.
- Evidence trail, not score.
- Arize Phoenix must be load-bearing: detector health events affect verdict influence.
- OSINT is the user-facing showstopper: provenance, sources, dates, research hops.
- Do not add more detectors or redesign the UI unless explicitly asked.

Current implemented hackathon additions:

- Phoenix/OpenTelemetry tracing in `backend/app/core/observability.py`.
- Detector health governor in `backend/app/core/health_governor.py`.
- Pipeline-level tracing and `pipeline_health` in `backend/app/core/pipeline.py`.
- Gemini-grounded OSINT research agent and optional public-URL reverse-image enrichment in `backend/app/core/llm_client.py`.
- Upgraded OSINT detector output in `backend/app/detectors/osint.py`.
- Agent Builder endpoints in `backend/app/main.py`: `/agent/analyze` and `/agent/chat`.
- Arize health endpoint in `backend/app/main.py`: `/arize/health`.
- Arize badge and OSINT research UI in `frontend/src/App.jsx`.
- `.env.example` documents required env vars.
- `mcp/phoenix-mcp.json` is the official Phoenix MCP server template.
- `ContextFiles/AgentBuilderPhoenixSetup.md` documents Agent Builder and Phoenix MCP setup.

Next highest-leverage work:

1. Deploy to Google Cloud Run.
2. Configure Phoenix Cloud and confirm traces arrive.
3. Configure Agent Builder tools against `/agent/analyze` and `/agent/chat`.
4. Connect the Phoenix MCP server using `mcp/phoenix-mcp.json`.
5. Run the Pope puffer demo image end to end.
6. Capture a prepared spectral circuit-breaker trace for the demo.
7. Update any final submission copy to emphasize “forensic investigation platform.”

Known caveat:

The local Codex environment used for the May 28 update did not have the PyTorch spectral runtime installed. Frontend build, Python compile, backend import, and a synthetic registered-pipeline analysis were verified, but spectral degraded to `error`. Re-test with full backend dependencies before the demo.
