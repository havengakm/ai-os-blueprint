#!/usr/bin/env bash
# Plan 1 acceptance harness - one-command orchestrator.
#
# Runs preflight -> run_daemon_once --dry-run -> verify, bailing out at
# the first failure. Prints the report path + exit code summary.
#
# Usage:
#   ./scripts/plan1_acceptance.sh <client-id>
#
# Exit codes:
#   0  AUTO PASS plus operator must tick the hallucination box
#      (verify returned 2) OR a clean end-to-end pass
#   1  AUTO FAIL - either preflight failed, run_daemon_once errored,
#      or verify detected an automated check failure
#   2  env missing / could not connect to Supabase

set -u

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <client-id>" >&2
    exit 1
fi

CLIENT_ID="$1"
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=================================================================="
echo "Plan 1 acceptance run - client_id=${CLIENT_ID}"
echo "=================================================================="

# ── Step 1: preflight ────────────────────────────────────────────────────
echo
echo "[1/3] Preflight (read-only seed-data checks)..."
echo
uv run python "${REPO_ROOT}/scripts/plan1_acceptance_preflight.py" \
    --client-id="${CLIENT_ID}"
PREFLIGHT_CODE=$?

if [[ ${PREFLIGHT_CODE} -eq 2 ]]; then
    echo
    echo "BLOCKED: required env vars missing. Fix .env and re-run." >&2
    exit 2
fi
if [[ ${PREFLIGHT_CODE} -ne 0 ]]; then
    echo
    echo "BLOCKED: preflight found failing checks. Fix the issues above" >&2
    echo "and re-run ./scripts/plan1_acceptance.sh ${CLIENT_ID}" >&2
    exit 1
fi

# ── Step 2: capture start timestamp + run daemon ─────────────────────────
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo "[2/3] Running daemon (dry-run)... started_at=${STARTED_AT}"
echo
uv run python "${REPO_ROOT}/scripts/run_daemon_once.py" \
    --client-id="${CLIENT_ID}" --dry-run
DAEMON_CODE=$?

if [[ ${DAEMON_CODE} -eq 2 ]]; then
    echo
    echo "BLOCKED: run_daemon_once could not find client_config for ${CLIENT_ID}." >&2
    echo "Expected preflight to catch this - re-check preflight output." >&2
    exit 1
fi
if [[ ${DAEMON_CODE} -ne 0 ]]; then
    echo
    echo "BLOCKED: at least one pipeline stage errored. Inspect the" >&2
    echo "daemon output above; verify will still run to emit a partial report." >&2
fi

# ── Step 3: verify ───────────────────────────────────────────────────────
echo
echo "[3/3] Verifying (querying decision_log)..."
echo
uv run python "${REPO_ROOT}/scripts/plan1_acceptance_verify.py" \
    --client-id="${CLIENT_ID}" --started-at="${STARTED_AT}"
VERIFY_CODE=$?

echo
echo "=================================================================="
echo "SUMMARY"
echo "=================================================================="
echo "preflight exit:    ${PREFLIGHT_CODE} (0 = pass)"
echo "run_daemon exit:   ${DAEMON_CODE} (0 = all stages ok)"
echo "verify exit:       ${VERIFY_CODE} (0 = auto pass clean, 2 = needs operator review)"
echo

if [[ ${VERIFY_CODE} -eq 1 ]]; then
    echo "RESULT: AUTO FAIL - do NOT merge Plan 1. See report for details."
    exit 1
fi
if [[ ${DAEMON_CODE} -ne 0 ]]; then
    echo "RESULT: DAEMON ERRORED - inspect report + daemon log, do NOT merge."
    exit 1
fi
if [[ ${VERIFY_CODE} -eq 2 ]]; then
    echo "RESULT: AUTOMATED CHECKS PASSED - operator must tick the"
    echo "        hallucination-probe checkbox in the report before merging."
    exit 0
fi

echo "RESULT: AUTO PASS."
exit 0
