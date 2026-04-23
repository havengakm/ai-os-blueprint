#!/usr/bin/env bash
# setup_client.sh — AIOS new-client onboarding orchestrator (Task 16b Step 3)
#
# Runs the full onboarding sequence for a fresh client deployment:
#   1. Seed autonomy rules (all 19 action_types at 'suggest')
#   2. Load expert knowledge into knowledge_base
#   3. Load client-specific context into business_context (+ resolve [[backlinks]])
#   4. Load component variants into component_variants
#   5. Configure Trigify monitors (intent + competitor + thought-leader + brand)
#
# Usage:
#     bash scripts/setup_client.sh <client-id> [--dry-run] [--no-confirm]
#
# Each sub-step exits non-zero on failure, and this script propagates the
# failure (fail-fast). Re-run after fixing issues; all sub-steps are
# idempotent.

set -euo pipefail

# --------------------------------------------------------------------------- #
# Help                                                                         #
# --------------------------------------------------------------------------- #

_usage() {
  cat <<'EOF'
Usage: bash scripts/setup_client.sh <client-id> [--dry-run] [--no-confirm]

Arguments:
  <client-id>      Required. Matches context/<client-id>/ directory name.

Options:
  --dry-run        Preview each step without writing to Supabase or Trigify.
  --no-confirm     Skip interactive confirm prompts (use for automation).
  -h, --help       Show this help and exit.

Required environment variables:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, VOYAGE_API_KEY,
  ANTHROPIC_API_KEY, TRIGIFY_API_KEY

Sequence:
  1/5 Seed autonomy rules        (scripts/seed_autonomy_rules.py)
  2/5 Load expert knowledge      (scripts/load_knowledge.py)
  3/5 Load client context        (scripts/load_context.py)
  4/5 Load component variants    (scripts/load_components.py)
  5/5 Configure Trigify monitors (scripts/configure_trigify_monitors.py)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  _usage
  exit 0
fi

# --------------------------------------------------------------------------- #
# Arg parsing                                                                  #
# --------------------------------------------------------------------------- #

if [[ $# -lt 1 ]]; then
  echo "ERROR: client-id required." >&2
  echo >&2
  _usage >&2
  exit 1
fi

CLIENT_ID="$1"
shift

PASSTHROUGH=()
for arg in "$@"; do
  case "$arg" in
    --dry-run|--no-confirm)
      PASSTHROUGH+=("$arg")
      ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      echo >&2
      _usage >&2
      exit 1
      ;;
  esac
done

# --------------------------------------------------------------------------- #
# Env-var check                                                                #
# --------------------------------------------------------------------------- #

REQUIRED_VARS=(
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  VOYAGE_API_KEY
  ANTHROPIC_API_KEY
  TRIGIFY_API_KEY
)
MISSING=()
for v in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    MISSING+=("$v")
  fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "ERROR: missing required environment variables: ${MISSING[*]}" >&2
  echo "Set them in .env (or export before running)." >&2
  exit 1
fi

# --------------------------------------------------------------------------- #
# Sequence                                                                     #
# --------------------------------------------------------------------------- #

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ">>> Step 1/5: Seeding autonomy rules for $CLIENT_ID"
uv run python "$SCRIPT_DIR/seed_autonomy_rules.py" \
  --client-id="$CLIENT_ID" "${PASSTHROUGH[@]}"

echo ""
echo ">>> Step 2/5: Loading expert knowledge (global)"
# Knowledge is client_id='global'; CLIENT_ID is not passed here.
uv run python "$SCRIPT_DIR/load_knowledge.py" "${PASSTHROUGH[@]}"

echo ""
echo ">>> Step 3/5: Loading client context for $CLIENT_ID"
uv run python "$SCRIPT_DIR/load_context.py" \
  --client-id="$CLIENT_ID" "${PASSTHROUGH[@]}"

echo ""
echo ">>> Step 4/5: Loading component variants for $CLIENT_ID"
uv run python "$SCRIPT_DIR/load_components.py" \
  --client-id="$CLIENT_ID" "${PASSTHROUGH[@]}"

echo ""
echo ">>> Step 5/5: Configuring Trigify monitors for $CLIENT_ID"
uv run python "$SCRIPT_DIR/configure_trigify_monitors.py" \
  --client-id="$CLIENT_ID" "${PASSTHROUGH[@]}"

# --------------------------------------------------------------------------- #
# Done                                                                         #
# --------------------------------------------------------------------------- #

echo ""
echo "Client $CLIENT_ID onboarding complete. Next step: run"
echo "  /discover-trigify-leads $CLIENT_ID"
echo "to do the first discovery pass."
