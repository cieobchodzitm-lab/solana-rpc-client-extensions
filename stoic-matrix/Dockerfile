# ═══════════════════════════════════════════════════════════════════════════════
# stoic-matrix — Multi-stage Dockerfile
# Angel Guardian Technologies / cieobchodzitm-lab
# ═══════════════════════════════════════════════════════════════════════════════
#
# Stages:
#   base-python  → shared Python layer (system deps + venv)
#   deps         → Python dependencies installed
#   test         → test runner (pytest, ruff, mypy)
#   hsa-agent    → production HSA-001 agent (minimal, no dev tools)
#   hf-space     → HuggingFace Space (FastAPI + frontend, port 7860, UID 1000)
#   ci-runner    → GitLab CI runner image (all tools: Rust, Node, Python, sccache)
#
# Usage:
#   # HF Space (production)
#   docker build --target hf-space -t stoic-matrix:hf .
#   docker run --rm -p 7860:7860 -e GEMINI_API_KEY=$GEMINI_API_KEY stoic-matrix:hf
#
#   # HSA agent only
#   docker build --target hsa-agent -t stoic-matrix:hsa .
#   docker run --rm -e GEMINI_API_KEY=$KEY stoic-matrix:hsa \
#     --agent-id test-001 --action "commit msg" --output-json /tmp/result.json
#
#   # CI runner (self-hosted GitLab runner base)
#   docker build --target ci-runner -t stoic-matrix:ci .
# ═══════════════════════════════════════════════════════════════════════════════

# ── Global ARGs ───────────────────────────────────────────────────────────────
ARG PYTHON_VERSION=3.11
ARG NODE_VERSION=20
ARG RUST_VERSION=1.78
ARG SCCACHE_VERSION=0.8.1
ARG UID=1000
ARG GID=1000

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 1: base-python — shared OS + Python foundation
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:${PYTHON_VERSION}-slim-bookworm AS base-python

ARG UID
ARG GID

# System deps (minimal, no build-essential at runtime)
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (HF Space requires UID 1000)
RUN groupadd --gid ${GID} appuser \
    && useradd --uid ${UID} --gid ${GID} --shell /bin/bash --create-home appuser

WORKDIR /app

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 2: deps — Python dependencies (cached layer)
# ═══════════════════════════════════════════════════════════════════════════════
FROM base-python AS deps

# Install build deps only for this stage
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (cache-friendly)
COPY requirements.txt .

# Install into venv (isolates from system Python)
RUN python -m venv /app/.venv \
    && /app/.venv/bin/pip install --upgrade pip --quiet \
    && /app/.venv/bin/pip install --no-cache-dir -r requirements.txt

ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 3: test — dev dependencies + test runner
# ═══════════════════════════════════════════════════════════════════════════════
FROM deps AS test

# Dev/test tools on top of prod deps
RUN /app/.venv/bin/pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    ruff \
    mypy \
    --quiet

# Copy full source
COPY --chown=appuser:appuser . .

USER appuser

# Default: run full test suite
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "--cov=.", "--cov-report=term-missing"]

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 4: hsa-agent — minimal HSA-001 production image
# ═══════════════════════════════════════════════════════════════════════════════
FROM base-python AS hsa-agent

ARG UID

# Copy venv from deps stage (no build tools needed)
COPY --from=deps /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy only the agent files
COPY --chown=appuser:appuser hsa_agent.py .
COPY --chown=appuser:appuser l7_memory_exporter.py . 2>/dev/null || true

USER appuser

# Output dir
RUN mkdir -p /app/hsa_assessments

VOLUME ["/app/hsa_assessments"]

ENTRYPOINT ["python", "hsa_agent.py"]
CMD ["--help"]

# ─── Labels ───────────────────────────────────────────────────────────────────
LABEL org.opencontainers.image.title="HSA-001 Virtue Audit Agent"
LABEL org.opencontainers.image.description="Stoic AI governance agent — Angel Guardian Technologies"
LABEL org.opencontainers.image.vendor="cieobchodzitm-lab"
LABEL maintainer="cieobchodzitm"

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 5: frontend-builder — Next.js / React build
# ═══════════════════════════════════════════════════════════════════════════════
FROM node:${NODE_VERSION}-slim AS frontend-builder

RUN npm install -g pnpm --quiet

WORKDIR /frontend

# Cache deps separately from source
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --store-dir /pnpm-store

COPY frontend/ .

ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm run build

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 6: hf-space — HuggingFace Space (FastAPI + static frontend)
#           UID=1000, port=7860 — HF Space requirements
# ═══════════════════════════════════════════════════════════════════════════════
FROM base-python AS hf-space

ARG UID

# Copy Python venv
COPY --from=deps /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# HF Space environment
ENV PORT=7860
ENV HOST=0.0.0.0

# Copy backend
COPY --chown=appuser:appuser hsa_agent.py .
COPY --chown=appuser:appuser l7_memory_exporter.py . 2>/dev/null || true

# Copy FastAPI app (cnota dashboard)
COPY --chown=appuser:appuser app/ ./app/ 2>/dev/null || true
COPY --chown=appuser:appuser main.py . 2>/dev/null || true

# Copy built frontend from builder stage
COPY --from=frontend-builder --chown=appuser:appuser \
    /frontend/out ./static/ 2>/dev/null || true
COPY --from=frontend-builder --chown=appuser:appuser \
    /frontend/.next/static ./.next/static/ 2>/dev/null || true

# Data directories
RUN mkdir -p /app/hsa_assessments /app/exports /app/data

USER appuser

EXPOSE 7860

# Healthcheck (HF Space expects 200 on /)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]

LABEL org.opencontainers.image.title="L7 CNOTA Dashboard"
LABEL org.opencontainers.image.description="Virtue Passport — HuggingFace Space"
LABEL org.opencontainers.image.vendor="cieobchodzitm-lab"
LABEL space.huggingface.sdk="docker"

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 7: ci-runner — self-hosted GitLab runner base image
#           All tools: Rust + sccache, Node/pnpm, Python, git, curl
# ═══════════════════════════════════════════════════════════════════════════════
FROM ubuntu:24.04 AS ci-runner

ARG RUST_VERSION
ARG SCCACHE_VERSION
ARG NODE_VERSION

ENV DEBIAN_FRONTEND=noninteractive
ENV RUSTUP_HOME=/usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo
ENV PATH=/usr/local/cargo/bin:$PATH
# RF-004: CARGO_INCREMENTAL=0 baked into image
ENV CARGO_INCREMENTAL=0

# ── System packages ───────────────────────────────────────────────────────────
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    ca-certificates \
    build-essential \
    pkg-config \
    libssl-dev \
    python3.12 \
    python3.12-venv \
    python3-pip \
    zstd \
    jq \
    && rm -rf /var/lib/apt/lists/*

# ── Rust ──────────────────────────────────────────────────────────────────────
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain ${RUST_VERSION} --no-modify-path \
    && rustup component add clippy rustfmt \
    && cargo --version \
    && rustc --version

# ── sccache (RF-002/RF-004: pre-installed, CARGO_INCREMENTAL=0 global) ────────
RUN curl -sL \
    "https://github.com/mozilla/sccache/releases/download/v${SCCACHE_VERSION}/sccache-v${SCCACHE_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
    | tar xz --strip-components=1 -C /usr/local/bin/ \
      "sccache-v${SCCACHE_VERSION}-x86_64-unknown-linux-musl/sccache" \
    && sccache --version

# ── Node.js + pnpm ────────────────────────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g pnpm \
    && node --version \
    && pnpm --version \
    && rm -rf /var/lib/apt/lists/*

# ── Python tools ──────────────────────────────────────────────────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    ruff \
    mypy \
    pytest \
    pytest-asyncio \
    google-genai \
    agentops \
    huggingface_hub

# ── gitlab-runner binary ──────────────────────────────────────────────────────
RUN curl -sL "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh" | bash \
    && apt-get install -y gitlab-runner \
    && gitlab-runner --version \
    && rm -rf /var/lib/apt/lists/*

# ── FastZip feature flag (RF-001: globally available) ─────────────────────────
ENV FF_USE_FASTZIP=true
ENV ARTIFACT_COMPRESSION_LEVEL=fast
ENV CACHE_COMPRESSION_LEVEL=fast

# ── verify_runner.sh pre-baked ────────────────────────────────────────────────
COPY scripts/verify_runner.sh /usr/local/bin/verify_runner
RUN chmod +x /usr/local/bin/verify_runner

# ── Runtime user for runner jobs ──────────────────────────────────────────────
RUN useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home runner 2>/dev/null || true

# Default: verify environment
CMD ["verify_runner"]

LABEL org.opencontainers.image.title="stoic-matrix CI Runner"
LABEL org.opencontainers.image.description="GitLab CI base image: Rust+sccache, Node, Python, gitlab-runner"
LABEL org.opencontainers.image.vendor="cieobchodzitm-lab"
