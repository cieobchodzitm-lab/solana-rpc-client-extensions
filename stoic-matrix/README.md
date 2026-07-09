# stoic-matrix

Angel Guardian Technologies — L7 / Rzeczpospolita governance stack.

## Contents

| Path | Description |
|---|---|
| `hsa_agent.py` | HSA-001 Virtue Audit Agent (Gemini 2.0 Flash backend) |
| `l7_memory_exporter.py` | L7 Memory JSON exporter with rule-based tag extraction |
| `requirements.txt` | Unified Python deps (Gemini + FastAPI + Postgres) |
| `Dockerfile` | Multi-stage build: `base-python` → `deps` → `test` / `hsa-agent` / `hf-space` / `ci-runner` |
| `docker-compose.yml` | Local stack: `hf-space`, `hsa-agent`, `postgres`, `otel-collector`, `ci-runner` |
| `.gitlab-ci.yml` | GitLab CI/CD with sccache (GCS), pnpm/pip caching, HSA gate |
| `test_scenarios.csv` | Bridge verdict test scenarios (TP-001…TP-006) |
| `docs/Layer_4_Technical_Specification.pdf` | Layer 4 technical spec |
| `nft-metadata/` | Stoic Matrix NFT collection metadata (18 JSON files, 4 tiers × 4 layers) |
| `landing/` | Marketing landing page (self-contained HTML) |

The GitHub workflow lives at repo root: `.github/workflows/hsa_virtue_audit.yml` — it runs on any change under `stoic-matrix/**`.

## Quick start

```bash
cd stoic-matrix

# ── Local HSA audit ──────────────────────────────────────────
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=…
python hsa_agent.py --agent-id local-001 \
  --action "Deployed L7 Bridge to mainnet" \
  --output-json ./hsa_assessments/result.json

# ── Docker stack ─────────────────────────────────────────────
docker compose up hf-space postgres           # dev
docker compose run --rm hsa-agent \
  --agent-id local-001 --action "test commit"  # one-shot audit
```

## HSA-001 output schema

```json
{
  "agent_id": "…",
  "tier": "PLATINUM | GOLD | SILVER | BRONZE | FAILED",
  "overall_score": 8.42,
  "proposed_virtues": { "courage": …, "wisdom": …, "justice": …, "temperance": … },
  "delta": { "has_baseline": true, "courage": +0.1, "overall": -0.3, … },
  "trend": "IMPROVED | STABLE | REGRESSED | UNKNOWN",
  "bridge_compliant": true,
  "requires_human_approval": false,
  "stoic_feedback": "…"
}
```

Weighted score: `wisdom·0.35 + justice·0.25 + courage·0.20 + temperance·0.20`.

Bridge compliance mirrors `L7BridgeGuard.sol`: `courage ≥ 7.0`, `wisdom ≥ 8.0`, `justice ≥ 6.0`.

## Env vars

| Variable | Required by | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `hsa_agent.py`, `hf-space` | Gemini backend |
| `AGENTOPS_API_KEY` | optional | AgentOps monitoring |
| `SCCACHE_GCS_BUCKET` + `SCCACHE_GCS_CREDENTIALS` | GitLab CI | sccache GCS backend |
| `GITLAB_API_TOKEN` | GitLab CI | posting HSA verdict as MR note |
| `HF_TOKEN` | GitLab deploy job | HuggingFace Space upload |

Never commit these — set them as CI/CD secrets or `.env` (git-ignored).

## Fixes applied when integrating

- `hsa_agent.py`: removed duplicate `add_mutually_exclusive_group` block (would raise `ArgumentError: conflicting option string: --action` on any invocation).
- Deduplicated identical uploads (`Dockerfile1` == `Dockerfile2`, `hsa_agent1.py` == `hsa_agent2.py`).
- GitHub workflow scoped to `paths: ['stoic-matrix/**']` so it doesn't run for `layer-4-core` or other subprojects.

## Known gaps — TODO before build

The following files are referenced by `Dockerfile` / `docker-compose.yml` but were not part of the upload; add them before building those stages:

| Referenced by | Path | Purpose |
|---|---|---|
| `Dockerfile` stage `ci-runner` L282 | `scripts/verify_runner.sh` | runner smoke test at `CMD ["verify_runner"]` |
| `docker-compose.yml` `postgres` | `db/init.sql` | Postgres init script |
| `docker-compose.yml` `otel-collector` | `otel/config.yaml` | OpenTelemetry collector config |
| `docker-compose.yml` `hf-space` | `main.py`, `app/` | FastAPI entrypoint served by uvicorn |
