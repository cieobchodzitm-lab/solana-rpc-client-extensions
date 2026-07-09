# Kubernetes MCP Server — setup for Claude Code

Attach `kubernetes-mcp-server` (mkm29 Go build) to Claude Code so the assistant can list, describe, apply, and delete Kubernetes resources through the Model Context Protocol.

## Prerequisites

1. **kubectl** installed and on `PATH`
2. **`~/.kube/config`** pointing at the cluster you want the assistant to reach
3. **Go 1.22+** *or* a pre-built binary from the [Releases page](https://github.com/mkm29/kubernetes-mcp-server/releases)

## Install the server binary

```bash
# Option A — go install (needs Go toolchain)
go install github.com/mkm29/kubernetes-mcp-server@latest
# binary lands in $(go env GOPATH)/bin

# Option B — pre-built release
curl -L -o /usr/local/bin/kubernetes-mcp-server \
  https://github.com/mkm29/kubernetes-mcp-server/releases/latest/download/kubernetes-mcp-server-linux-amd64
chmod +x /usr/local/bin/kubernetes-mcp-server

# Sanity check
kubernetes-mcp-server --help
```

## Verify the cluster is reachable

```bash
kubectl cluster-info                # cluster URL
kubectl get ns                      # basic RBAC works
```

If either fails, fix `~/.kube/config` first — the MCP server is a thin wrapper and cannot recover from bad credentials.

## Wire it into Claude Code

Add the `mcpServers` block to `~/.claude/settings.json`:

```json
{
    "$schema": "https://json.schemastore.org/claude-code-settings.json",
    "permissions": { "allow": ["Skill"] },
    "mcpServers": {
        "kubernetes": {
            "command": "kubernetes-mcp-server",
            "args": ["--kubeconfig", "${HOME}/.kube/config"],
            "env": { "KUBECONFIG": "${HOME}/.kube/config" }
        }
    }
}
```

Restart Claude Code. The next session shows the server as `mcp__kubernetes__*` tools in `ToolSearch`.

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `Could not attach to MCP server Kubernetes MCP Server` | `command` not on `PATH` at session start | Use absolute path in `command`, or reload PATH before starting Claude Code |
| `permission denied` on `kubernetes-mcp-server` | binary not executable | `chmod +x $(which kubernetes-mcp-server)` |
| Server starts, tools list is empty | `~/.kube/config` unreadable by the process | `chmod 600 ~/.kube/config`; verify `$USER` owns it |
| `Unable to connect to the server: dial tcp …: i/o timeout` | cluster unreachable from this host | VPN / bastion / firewall — same debug as `kubectl` itself |
| Works locally, fails on Claude Code on Web | remote container has no kubectl or kubeconfig | This MCP server is meant for local Claude Code CLI; on Web, spin up an MCP proxy that exposes your cluster or expose the cluster URL directly |

## Remote-execution environments

Claude Code on Web sessions run in ephemeral containers that reset between sessions. `~/.claude/settings.json` written during a session does **not** persist. Configure MCP in your **local** Claude Code CLI, not on the Web session.

If you need cluster access from the Web session specifically:

1. Expose a stable proxy endpoint (e.g. `kubectl proxy` behind a public tunnel, or a self-hosted `mcp-remote` gateway),
2. Configure the MCP server as an HTTP transport pointing at that endpoint,
3. Never expose `~/.kube/config` credentials directly to the remote session.
