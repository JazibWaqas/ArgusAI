# Agent Builder and Phoenix MCP Setup

Last updated: May 29, 2026.

This project exposes backend endpoints for Google Cloud Agent Builder and includes a Phoenix MCP config template.

## Agent Builder Tools

Create two tools in Google Cloud Agent Builder.

### analyze_image

HTTP endpoint:

Current backend:

`https://argusai-backend-1007754127412.us-central1.run.app`

Endpoint:

`POST https://argusai-backend-1007754127412.us-central1.run.app/agent/analyze`

Multipart form fields:

- `file`: image upload
- `context`: optional user claim or public image URL

Returns:

- `session_id`
- `verdict`
- `certainty`
- `confidence_label`
- `short_summary`
- `top_signals`
- `osint_summary`
- `model_health`
- `arize_health`

### ask_question

HTTP endpoint:

`POST https://argusai-backend-1007754127412.us-central1.run.app/agent/chat`

JSON body:

```json
{
  "session_id": "session id returned by analyze_image",
  "message": "Why did OSINT matter here?"
}
```

## Phoenix MCP

Template config:

`mcp/phoenix-mcp.json`

It uses the official Arize Phoenix MCP server package:

`@arizeai/phoenix-mcp`

The MCP connection is used for Phoenix prompts, datasets, and experiments during the Agent Builder/Arize workflow. Runtime tracing is handled by `arize-phoenix-otel` in the backend.

## Local Self-Hosted Phoenix

The Arize hosted signup flow was unreliable during setup, so the current working fallback is self-hosted Phoenix through Docker.

Start Phoenix:

```powershell
docker compose -f docker-compose.phoenix.yml up -d
```

Local URLs:

- Phoenix UI: `http://localhost:6006`
- HTTP collector: `http://localhost:6006/v1/traces`
- gRPC collector: `http://localhost:4317`

Local `.env` should use:

```env
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
PHOENIX_PROJECT_NAME=argusai-forensics
PHOENIX_DASHBOARD_URL=http://localhost:6006
ARIZE_HEALTH_GOVERNOR=1
```

No `PHOENIX_API_KEY` is needed for the local Docker setup.

Verified on May 29, 2026:

- Phoenix container `argusai-phoenix` is running.
- UI returns HTTP 200.
- Backend tracing initializes with `enabled=True`.
- Phoenix logs show successful `POST /v1/traces` traffic from a local ArgusAI smoke run.

## Phoenix Cloud

Phoenix env vars are not configured on Cloud Run yet. Add these once the Arize account is ready:

- `PHOENIX_API_KEY`
- `PHOENIX_COLLECTOR_ENDPOINT`
- `PHOENIX_DASHBOARD_URL`

Cloud Run should use Phoenix Cloud rather than `localhost`, because `localhost` inside Cloud Run would point to the Cloud Run container itself, not this laptop's Phoenix container.

## Demo Use

For the 3-minute video, do not spend more than 10-15 seconds on Agent Builder. Show that the agent can call `analyze_image`, then return to the full ArgusAI UI and Phoenix trace.

The main Arize proof is the detector health trace and reliability governor, not the Agent Builder configuration screen. If Phoenix Cloud is still unavailable, use local Phoenix in the recording and state that the demo is self-hosted Phoenix using the same OpenTelemetry trace path.
