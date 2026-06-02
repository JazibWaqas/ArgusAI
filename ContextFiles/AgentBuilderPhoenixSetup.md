# Agent Builder and Phoenix MCP Setup

Last updated: June 2, 2026.

Read `ContextFiles/CurrentHandoff.md` first for the complete deployed state.

## Current URLs

- Frontend: `https://argusai-frontend-1007754127412.us-central1.run.app`
- Backend: `https://argusai-backend-1007754127412.us-central1.run.app`
- Phoenix UI/base URL: `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app`
- Phoenix OTEL collector: `https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces`
- Admin dashboard password: `argusai2026`

## Agent Builder Tools

Current practical route for the demo: use the repo-local Google ADK agent in `agents/argusai_investigator`. It is code-first, uses Gemini, connects to Phoenix MCP locally through `npx @arizeai/phoenix-mcp`, and calls ArgusAI backend tools. This avoids manual console setup blocking the recording.

Run locally:

```powershell
uv venv .venv-adk
uv pip install --python .venv-adk\Scripts\python.exe -r agents\argusai_investigator\requirements.txt
$env:ARGUSAI_API_BASE="http://127.0.0.1:8000"
$env:ADK_GEMINI_MODEL="gemini-3.5-flash"
.\.venv-adk\Scripts\adk.exe run agents\argusai_investigator
```

Verified locally:

- ADK agent imported successfully with 10 tools.
- Phoenix MCP server starts over stdio.
- ADK called `phoenix_list-projects` and `phoenix_list-traces`.
- Phoenix returned project `argusai-forensics` with internal ID `UHJvamVjdDoy` and real traces/spans.

If Gemini 3.5 returns temporary `503 high demand`, use `ADK_GEMINI_MODEL=gemini-2.5-flash` for the recording fallback.

Create two tools in Google Cloud Agent Builder.

### Tool 1: analyze_media

Endpoint:

```text
POST https://argusai-backend-1007754127412.us-central1.run.app/agent/analyze
```

Multipart form fields:

- `file`: image/video/audio upload
- `context`: optional user claim, speaker/event context, or public source URL

Returns:

- `session_id`
- `media_type`
- `verdict`
- `certainty`
- `confidence_label`
- `short_summary`
- `phoenix_trace_id`
- `history_context`
- `top_signals`
- `osint_summary`
- `model_health`
- `arize_health`

Important: this endpoint now queries Firestore before responding. `history_context` includes total persisted analyses, same-media analysis counts, detector reliability for the current report's signals, recent same-media cases, and Phoenix trace IDs. This is what lets Agent Builder answer from ArgusAI's accumulated forensic history instead of acting like a generic Gemini wrapper.

Use description:

```text
Analyze an uploaded image, video, or audio clip with ArgusAI. Use this tool when the user wants to verify whether media is authentic, AI-generated, synthetic, manipulated, or needs provenance investigation. Include any user claim as context.
```

### Tool 2: ask_forensic_followup

Endpoint:

```text
POST https://argusai-backend-1007754127412.us-central1.run.app/agent/chat
```

JSON body:

```json
{
  "session_id": "session id returned by analyze_media",
  "message": "Why did OSINT matter here?"
}
```

Use description:

```text
Ask a follow-up question about the previous ArgusAI analysis. Use this after analyze_media returns a session_id. The answer uses the current forensic evidence plus Firestore history context such as accumulated detector reliability and recent same-media cases.
```

Recommended Agent Builder instruction:

```text
You are ArgusAI, a forensic investigation agent. Do not describe the product as a simple classifier. Use analyze_media for media authenticity questions. Use ask_forensic_followup for follow-up questions after analysis. Emphasize evidence trail, OSINT provenance, detector reliability, Firestore history, and Phoenix auditability. If history_context is present, use it to explain accumulated reliability, but do not overclaim legal certainty.
```

## Phoenix MCP

Template config:

```text
mcp/phoenix-mcp.json
```

Current template:

```json
{
  "mcpServers": {
    "phoenix": {
      "command": "npx",
      "args": [
        "-y",
        "@arizeai/phoenix-mcp@latest",
        "--baseUrl",
        "${PHOENIX_DASHBOARD_URL}",
        "--apiKey",
        "${PHOENIX_API_KEY}"
      ]
    }
  }
}
```

For the current self-hosted Phoenix Cloud Run setup:

```env
PHOENIX_DASHBOARD_URL=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app
PHOENIX_API_KEY=
```

Important: the MCP `--baseUrl` should be the Phoenix UI/base URL, not `/v1/traces`. The OTEL collector endpoint is only for backend tracing.

If the Agent Builder/MCP UI rejects a blank API key for self-hosted Phoenix, manually remove the `--apiKey` and `${PHOENIX_API_KEY}` args from the MCP server config for that environment.

## Phoenix Runtime Tracing

Backend tracing is already configured on Cloud Run:

```env
PHOENIX_COLLECTOR_ENDPOINT=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app/v1/traces
PHOENIX_DASHBOARD_URL=https://argusai-phoenix-ddmxiumrdq-uc.a.run.app
PHOENIX_PROJECT_NAME=argusai-forensics
ARIZE_HEALTH_GOVERNOR=1
```

Verified:

- `GET /arize/health` shows tracing configured/enabled.
- `GET /arize/traces?limit=10` returns Firestore-backed recent image/audio/video traces.
- Phoenix Cloud Run logs show repeated `POST /v1/traces` HTTP 200.

Phoenix trace IDs are surfaced in:

- frontend verdict card
- expanded signal details
- admin trace table
- official PDF footer
- Firestore analysis records
- Agent Builder responses

## Local Self-Hosted Phoenix Fallback

Start local Phoenix:

```powershell
docker compose -f docker-compose.phoenix.yml up -d
```

Local URLs:

- Phoenix UI: `http://localhost:6006`
- HTTP collector: `http://localhost:6006/v1/traces`
- gRPC collector: `http://localhost:4317`

Local `.env`:

```env
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
PHOENIX_PROJECT_NAME=argusai-forensics
PHOENIX_DASHBOARD_URL=http://localhost:6006
ARIZE_HEALTH_GOVERNOR=1
```

No `PHOENIX_API_KEY` is needed for local Phoenix.

## Demo Use

For the 3-minute video, spend only 10-20 seconds on Agent Builder:

1. Show Agent Builder has tools for `analyze_media` and `ask_forensic_followup`.
2. Run one quick call or show the successful configuration.
3. Return to the ArgusAI frontend/admin panel.

The main Arize proof is Phoenix-backed detector health, chain-of-custody links, and the admin trace view, not the Agent Builder configuration screen.
