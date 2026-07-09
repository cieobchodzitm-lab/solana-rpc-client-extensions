# HuggingFace MCP Server — setup for Claude Code

Attach the official HuggingFace MCP server so Claude can search models/datasets/spaces, read model cards, upload files to your HF Space, and manage repositories through the Model Context Protocol.

## Two auth modes

The HF MCP server accepts either an OAuth browser login or a static Bearer token. Pick one — do not configure both.

### Option A — OAuth login (recommended for local dev)

One-shot CLI:

```bash
claude mcp add hf-mcp-server -t http https://huggingface.co/mcp?login
```

The `?login` query kicks off an OAuth flow in your browser on the next Claude Code session; the token is stored by Claude Code and refreshed automatically.

Equivalent `~/.claude/settings.json`:

```json
{
    "mcpServers": {
        "hf-mcp-server": {
            "transport": "http",
            "url": "https://huggingface.co/mcp?login"
        }
    }
}
```

### Option B — Bearer token (recommended for CI / headless / remote)

One-shot CLI:

```bash
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxx
claude mcp add hf-mcp-server \
  -t http https://huggingface.co/mcp \
  -H "Authorization: Bearer $HF_TOKEN"
```

Equivalent `~/.claude/settings.json`:

```json
{
    "mcpServers": {
        "hf-mcp-server": {
            "transport": "http",
            "url": "https://huggingface.co/mcp",
            "headers": {
                "Authorization": "Bearer ${HF_TOKEN}"
            }
        }
    }
}
```

Create the token at <https://huggingface.co/settings/tokens>. Scope it to only what you need — for stoic-matrix's HF Space deploy you need `write` on the target repo; for read-only browsing `read` is enough.

## Verify

After restart, Claude Code exposes `mcp__hf-mcp-server__*` tools via `ToolSearch`. Sanity test:

```
list my huggingface spaces
```

## Integration with stoic-matrix

The `.gitlab-ci.yml` `deploy:hf-space` job already uses `HF_TOKEN` to push to `cieobchodzitm/l7-cnota-dashboard`. Reuse the same token for the MCP server so a single secret rotation covers both channels. Add `HF_TOKEN` to:

- Local shell / `.env` (for local Claude Code sessions)
- GitLab CI/CD → Settings → Variables (masked, protected)
- GitHub Actions → Repository Settings → Secrets

Never commit the token — it is not committed by these instructions; the `${HF_TOKEN}` placeholder is resolved by Claude Code at MCP start time from your environment.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Could not attach to MCP server hf-mcp-server` (401) | `HF_TOKEN` unset or expired | Regenerate at `huggingface.co/settings/tokens`; re-export |
| `Could not attach to MCP server hf-mcp-server` (403) | Token scope too narrow | Give the token `write` scope for the target repo |
| Attach succeeds but every tool call 401s | `Authorization` header not forwarded due to a stale cached config | Restart Claude Code; check `~/.claude/settings.json` picked up the `headers` block |
| Attach fails only in Claude Code on Web | Remote container has no `HF_TOKEN` env var | Set it via the environment's env-vars configuration, or switch to Option A OAuth flow if the Web environment supports interactive login |
