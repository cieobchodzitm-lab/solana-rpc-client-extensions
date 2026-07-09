#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# verify_runner.sh — smoke test for stoic-matrix ci-runner image
# Angel Guardian Technologies / cieobchodzitm-lab
# ═══════════════════════════════════════════════════════════════════════════════
#
# Runs at container start (default CMD) to confirm every tool the .gitlab-ci.yml
# expects is on PATH and executable. Non-zero exit → the image is broken,
# fail fast rather than have a job discover it mid-pipeline.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

FAIL=0

check() {
  local label=$1
  local cmd=$2
  if out=$(eval "$cmd" 2>&1); then
    printf "  ✅ %-20s %s\n" "$label" "$(echo "$out" | head -1)"
  else
    printf "  ❌ %-20s %s\n" "$label" "MISSING or FAILED"
    FAIL=$((FAIL + 1))
  fi
}

echo "═══ stoic-matrix ci-runner verification ═══"

echo "── System ──"
check "bash"        "bash --version | head -1"
check "git"         "git --version"
check "curl"        "curl --version | head -1"
check "wget"        "wget --version | head -1"
check "jq"          "jq --version"

echo "── Rust toolchain ──"
check "rustc"       "rustc --version"
check "cargo"       "cargo --version"
check "clippy"      "cargo clippy --version"
check "rustfmt"     "cargo fmt --version"
check "sccache"     "sccache --version"

echo "── Node toolchain ──"
check "node"        "node --version"
check "npm"         "npm --version"
check "pnpm"        "pnpm --version"

echo "── Python toolchain ──"
check "python3"     "python3 --version"
check "pip"         "pip3 --version"
check "ruff"        "ruff --version"
check "mypy"        "mypy --version"
check "pytest"      "pytest --version | head -1"

echo "── CI ──"
check "gitlab-runner" "gitlab-runner --version | head -1"

echo "── Env flags (RF-001/RF-004) ──"
printf "  CARGO_INCREMENTAL   = %s (expect 0)\n" "${CARGO_INCREMENTAL:-<unset>}"
printf "  FF_USE_FASTZIP      = %s (expect true)\n" "${FF_USE_FASTZIP:-<unset>}"
printf "  RUSTUP_HOME         = %s\n" "${RUSTUP_HOME:-<unset>}"
printf "  CARGO_HOME          = %s\n" "${CARGO_HOME:-<unset>}"

if [ "${CARGO_INCREMENTAL:-1}" != "0" ]; then
  echo "  ⚠️  CARGO_INCREMENTAL != 0 — sccache will emit cache misses"
  FAIL=$((FAIL + 1))
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "✅ Runner verification PASSED"
  exit 0
fi
echo "❌ Runner verification FAILED ($FAIL check(s))"
exit 1
