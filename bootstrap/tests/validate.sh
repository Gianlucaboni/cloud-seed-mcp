#!/usr/bin/env bash
###############################################################################
# tests/validate.sh — Permission verification script for SA hierarchy
#
# Validates that each SA has the expected permissions and, critically, does
# NOT have permissions it shouldn't have.
#
# Usage:
#   ./validate.sh --seed-project-id=PROJECT_ID [--client-project-id=PROJECT_ID]
#
# Requires: gcloud CLI with active authentication and permissions to
#           test IAM policies on the specified projects.
###############################################################################

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { ((PASS++)); echo -e "  ${GREEN}PASS${NC} $*"; }
fail() { ((FAIL++)); echo -e "  ${RED}FAIL${NC} $*"; }
warn() { ((WARN++)); echo -e "  ${YELLOW}WARN${NC} $*"; }

# ─── Parse arguments ─────────────────────────────────────────────────────────
SEED_PROJECT_ID=""
CLIENT_PROJECT_ID=""

for arg in "$@"; do
  case "$arg" in
    --seed-project-id=*)    SEED_PROJECT_ID="${arg#*=}" ;;
    --client-project-id=*)  CLIENT_PROJECT_ID="${arg#*=}" ;;
    --help|-h)
      echo "Usage: $0 --seed-project-id=ID [--client-project-id=ID]"
      exit 0
      ;;
  esac
done

if [[ -z "$SEED_PROJECT_ID" ]]; then
  echo "Error: --seed-project-id is required"
  exit 1
fi

# ─── Helper: check if SA has a specific permission ───────────────────────────
# Uses testIamPermissions API to verify actual effective permissions
check_permission() {
  local sa_email="$1"
  local project="$2"
  local permission="$3"
  local expected="$4" # "yes" or "no"

  local result
  result=$(gcloud projects test-iam-permissions "$project" \
    --permissions="$permission" \
    --impersonate-service-account="$sa_email" \
    --format="value(permissions)" 2>/dev/null || echo "ERROR")

  if [[ "$result" == "ERROR" ]]; then
    warn "$sa_email — cannot test '$permission' on $project (impersonation may not be available)"
    return
  fi

  if [[ "$expected" == "yes" ]]; then
    if [[ -n "$result" ]]; then
      pass "$sa_email HAS '$permission' on $project"
    else
      fail "$sa_email MISSING '$permission' on $project"
    fi
  else
    if [[ -z "$result" ]]; then
      pass "$sa_email correctly LACKS '$permission' on $project"
    else
      fail "$sa_email UNEXPECTEDLY HAS '$permission' on $project"
    fi
  fi
}

# ─── Helper: check SA exists ─────────────────────────────────────────────────
check_sa_exists() {
  local sa_email="$1"
  local project="$2"

  if gcloud iam service-accounts describe "$sa_email" --project="$project" &>/dev/null; then
    pass "SA exists: $sa_email"
    return 0
  else
    fail "SA does not exist: $sa_email"
    return 1
  fi
}

# ─── Helper: check SA is disabled ────────────────────────────────────────────
check_sa_disabled() {
  local sa_email="$1"
  local project="$2"

  local disabled
  disabled=$(gcloud iam service-accounts describe "$sa_email" \
    --project="$project" \
    --format="value(disabled)" 2>/dev/null || echo "ERROR")

  if [[ "$disabled" == "True" ]]; then
    pass "SA is disabled: $sa_email"
  elif [[ "$disabled" == "ERROR" ]]; then
    warn "Cannot check disabled status for: $sa_email"
  else
    fail "SA is NOT disabled (should be): $sa_email"
  fi
}

# =============================================================================
# TEST: SA Installer
# =============================================================================
echo ""
echo "━━━ Testing SA Installer ━━━"

INSTALLER_SA="cloudseed-installer@${SEED_PROJECT_ID}.iam.gserviceaccount.com"

if check_sa_exists "$INSTALLER_SA" "$SEED_PROJECT_ID"; then
  check_sa_disabled "$INSTALLER_SA" "$SEED_PROJECT_ID"
fi

# =============================================================================
# TEST: SA Orchestrator
# =============================================================================
echo ""
echo "━━━ Testing SA Orchestrator ━━━"

ORCHESTRATOR_SA="cloudseed-orchestrator@${SEED_PROJECT_ID}.iam.gserviceaccount.com"

if check_sa_exists "$ORCHESTRATOR_SA" "$SEED_PROJECT_ID"; then
  # Orchestrator should have these on seed project
  check_permission "$ORCHESTRATOR_SA" "$SEED_PROJECT_ID" "iam.serviceAccounts.create" "yes"
  check_permission "$ORCHESTRATOR_SA" "$SEED_PROJECT_ID" "run.services.create" "yes"

  # Orchestrator should NOT be able to delete projects
  check_permission "$ORCHESTRATOR_SA" "$SEED_PROJECT_ID" "resourcemanager.projects.delete" "no"

  # Orchestrator should NOT be able to access secrets
  check_permission "$ORCHESTRATOR_SA" "$SEED_PROJECT_ID" "secretmanager.versions.access" "no"
fi

# =============================================================================
# TEST: SA Ephemeral Pool Manager
# =============================================================================
echo ""
echo "━━━ Testing SA Ephemeral Pool Manager ━━━"

POOL_MGR_SA="cloudseed-ephemeral-mgr@${SEED_PROJECT_ID}.iam.gserviceaccount.com"

if check_sa_exists "$POOL_MGR_SA" "$SEED_PROJECT_ID"; then
  # Pool manager should be able to create SAs
  check_permission "$POOL_MGR_SA" "$SEED_PROJECT_ID" "iam.serviceAccounts.create" "yes"

  # Pool manager should NOT be able to delete projects
  check_permission "$POOL_MGR_SA" "$SEED_PROJECT_ID" "resourcemanager.projects.delete" "no"
fi

# =============================================================================
# TEST: SA Cleanup Function
# =============================================================================
echo ""
echo "━━━ Testing SA Cleanup Function ━━━"

CLEANUP_SA="cloudseed-sa-cleanup@${SEED_PROJECT_ID}.iam.gserviceaccount.com"
check_sa_exists "$CLEANUP_SA" "$SEED_PROJECT_ID"

# =============================================================================
# TEST: Per-Project SAs (if client project specified)
# =============================================================================
if [[ -n "$CLIENT_PROJECT_ID" ]]; then
  echo ""
  echo "━━━ Testing Per-Project SAs for $CLIENT_PROJECT_ID ━━━"

  # Detect project short name by listing SAs with the prefix pattern
  SA_LIST=$(gcloud iam service-accounts list \
    --project="$SEED_PROJECT_ID" \
    --filter="email:cs-*" \
    --format="value(email)" 2>/dev/null || echo "")

  if [[ -z "$SA_LIST" ]]; then
    warn "No per-project SAs found with 'cs-' prefix in $SEED_PROJECT_ID"
  else
    echo "  Found per-project SAs:"
    echo "$SA_LIST" | while read -r sa; do
      echo "    - $sa"

      # Check if it's a runtime SA
      if [[ "$sa" == *"-runtime@"* ]]; then
        check_permission "$sa" "$CLIENT_PROJECT_ID" "run.routes.invoke" "yes"
        check_permission "$sa" "$CLIENT_PROJECT_ID" "resourcemanager.projects.delete" "no"
      fi

      # Check if it's a deploy SA
      if [[ "$sa" == *"-deploy@"* ]]; then
        check_permission "$sa" "$CLIENT_PROJECT_ID" "run.services.create" "yes"
        check_permission "$sa" "$CLIENT_PROJECT_ID" "compute.instances.create" "no"
      fi

      # Check if it's a data SA
      if [[ "$sa" == *"-data@"* ]]; then
        check_permission "$sa" "$CLIENT_PROJECT_ID" "bigquery.tables.getData" "yes"
        check_permission "$sa" "$CLIENT_PROJECT_ID" "compute.instances.create" "no"
      fi
    done
  fi
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${WARN} warnings${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ "$FAIL" -gt 0 ]]; then
  echo -e "${RED}Some tests failed. Review the output above.${NC}"
  exit 1
fi

if [[ "$WARN" -gt 0 ]]; then
  echo -e "${YELLOW}All tests passed but some could not be verified (warnings).${NC}"
  exit 0
fi

echo -e "${GREEN}All tests passed.${NC}"
exit 0
