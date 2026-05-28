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
- Backend Cloud Run service is live at `https://argusai-backend-1007754127412.us-central1.run.app`.
- Spectral weights are stored at `gs://argusai-497719-models/models/argusai_best_weights.pth`.
- Local self-hosted Phoenix is working through `docker-compose.phoenix.yml` at `http://localhost:6006`.
- Local `.env` points tracing to `http://localhost:6006/v1/traces`; Phoenix logs confirmed successful trace POSTs.

Next highest-leverage work:

1. Run a real Cloud Run `/analyze` request to verify lazy model download and detector behavior.
2. Deploy the frontend with `VITE_API_BASE=https://argusai-backend-1007754127412.us-central1.run.app`.
3. Configure Phoenix Cloud env vars and confirm traces arrive, or keep using verified self-hosted Phoenix for the recorded demo if hosted Arize remains blocked.
4. Configure Agent Builder tools against `/agent/analyze` and `/agent/chat`.
5. Connect the Phoenix MCP server using `mcp/phoenix-mcp.json`.
6. Run the Pope puffer demo image end to end.
7. Capture a prepared spectral circuit-breaker trace for the demo.
8. Update any final submission copy to emphasize “forensic investigation platform.”

Known caveat:

Cloud Run uses `min-instances=0` to avoid idle spend, so first requests may cold start. Keep it that way during setup; switch to `min-instances=1` only near demo/judging if needed.

Cloud Run cannot use `http://localhost:6006` for Phoenix. That local URL only works on the laptop. Cloud Run needs Phoenix Cloud or another publicly reachable Phoenix collector.
