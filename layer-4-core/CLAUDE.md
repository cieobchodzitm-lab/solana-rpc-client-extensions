# CLAUDE.md — Layer 4 Core Developer Guide

## Project Overview

Layer 4 Core is a cognitive security REST API built on Claude Opus 4.7. It analyzes messages for psychological manipulation patterns and returns structured JSON results with a threat score, detected patterns, and Stoic-philosophy-based guidance.

## Key Commands

```bash
npm install          # install dependencies
npm run build        # compile TypeScript → dist/
npm start            # run Express server (PORT=3000 by default)
npm run analyze "…"  # run CLI one-shot analysis
DEBUG_BLOCKS=1 npm start  # enable verbose API block logging
```

## Architecture

```
src/
  system-prompt.ts  — full Layer 4 Core system prompt (cached via prompt caching)
  analyze.ts        — core Claude API call + code execution loop
  types.ts          — TypeScript types: AnalysisResult, BashStep, EditorStep
  server.ts         — Express REST API (/health, /analyze)
  index.ts          — CLI entry point
public/
  index.html        — single-file web UI
```

## Claude API Integration

**Model:** `claude-opus-4-7`  
**Thinking:** `{ type: "adaptive" }` (no budget_tokens — adaptive is the standard)  
**Tool:** `code_execution_20260120` (server-side REPL for linguistic analysis)  
**Prompt caching:** System prompt is wrapped in `TextBlockParam[]` with `cache_control: { type: "ephemeral" }` — cache hits are logged via `cache_read_input_tokens` in DEBUG mode.

The core loop in `analyze.ts`:
1. Safety check — physical danger keywords trigger an immediate plain-text override before any API call.
2. Stream a Claude request with the cached system prompt.
3. If `stop_reason === "pause_turn"` (server-side tool loop limit hit), re-send the conversation and continue. Up to `MAX_CONTINUATIONS = 5` times.
4. Collect `bash_code_execution_tool_result` and `text_editor_code_execution_tool_result` blocks into `CodeExecutionStep[]`.
5. Parse the last text block as JSON → `AnalysisResult`.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `LAYER4_API_KEY` | No | If set, every `/analyze` request must supply `X-API-Key: <value>` |
| `PORT` | No | HTTP port (default 3000) |
| `DEBUG_BLOCKS` | No | Set to `1` to log raw API blocks and usage stats to stderr |

## REST API

### `GET /health`
Always public. Returns `{ status, service, auth }`.

### `POST /analyze`
Protected by `X-API-Key` header when `LAYER4_API_KEY` is set.

Request body:
```json
{ "message": "<text to analyze>" }
```

Success (200):
```json
{
  "threat_score": 72,
  "primary_intent": "Guilt-based compliance extraction",
  "detected_patterns": ["Guilt-Tripping", "False Urgency"],
  "analysis_summary": "…",
  "stoic_nudge": "…",
  "suggested_action": "…",
  "code_execution_steps": [...]
}
```

Safety override (200):
```json
{ "safety_alert": true, "message": "SAFETY ALERT: …" }
```

## Docker

```bash
docker build -t layer-4-core .
docker run -e ANTHROPIC_API_KEY=… -p 3000:3000 layer-4-core

# or with docker-compose (reads .env)
docker compose up
```

## Deploy Configs

| Platform | File | Notes |
|---|---|---|
| Railway | `railway.json` | Dockerfile builder, `/health` check |
| Render | `render.yaml` | `starter` plan, autoDeploy |
| Fly.io | `fly.toml` | Warsaw region (`waw`), 512 MB VM |

Set `ANTHROPIC_API_KEY` and `LAYER4_API_KEY` as secrets in each platform's dashboard — never commit them.

## Security Notes

- **XSS:** Pattern tags in the web UI are rendered via `createElement`/`textContent`, not `innerHTML`.
- **Error leakage:** The 500 handler logs the full error server-side and returns only `"Internal server error"` to clients.
- **CORS:** Currently open (`*`). Restrict with `cors({ origin: "https://your-domain.com" })` in production.
- **Rate limiting:** No rate limiter is included. Add `express-rate-limit` before exposing publicly to control cost.
- **Prompt injection:** User input is triple-quote delimited in the prompt. The safety keyword check runs before any API call for physical-danger content.
- **Safety filter:** The keyword-based `checkPhysicalSafety()` is a first-pass guard only; it is easily bypassed. Do not treat it as the sole safety control.

## TypeScript Notes

- `response.usage` is cast via `as unknown as Record<string, number>` to access `cache_creation_input_tokens` and `cache_read_input_tokens` which are present at runtime but absent from the current SDK type.
- All code execution result block types (`BashCodeExecutionToolResultBlock`, `TextEditorCodeExecutionToolResultBlock`, etc.) require `@anthropic-ai/sdk ^0.82.0`.
