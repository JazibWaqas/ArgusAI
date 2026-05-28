# Agent Builder and Phoenix MCP Setup

Last updated: May 28, 2026.

This project exposes backend endpoints for Google Cloud Agent Builder and includes a Phoenix MCP config template.

## Agent Builder Tools

Create two tools in Google Cloud Agent Builder.

### analyze_image

HTTP endpoint:

`POST https://<cloud-run-url>/agent/analyze`

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

`POST https://<cloud-run-url>/agent/chat`

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

## Demo Use

For the 3-minute video, do not spend more than 10-15 seconds on Agent Builder. Show that the agent can call `analyze_image`, then return to the full ArgusAI UI and Phoenix trace.

The main Arize proof is the detector health trace and reliability governor, not the Agent Builder configuration screen.
