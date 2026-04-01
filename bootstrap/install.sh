#!/usr/bin/env bash
###############################################################################
# install.sh — Cloud Seed MCP Bootstrap Script
#
# One-time installation script that:
#   1. Validates prerequisites (gcloud, terraform, authentication)
#   2. Runs terraform init + plan + apply to create the SA hierarchy
#   3. Disables the Installer SA after successful bootstrap
#
# Usage:
#   ./install.sh --seed-project-id=my-seed-project --org-id=123456789
#
# The Installer SA is DISABLED (not deleted) after this script completes.
# This is irreversible without manual intervention — by design.
###############################################################################

set -euo pipefail

# ─── Colors and formatting ───────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()  { echo -e "\n${GREEN}━━━ $* ━━━${NC}\n"; }

# ─── Parse arguments ─────────────────────────────────────────────────────────
SEED_PROJECT_ID=""
ORG_ID=""
BILLING_ACCOUNT_ID=""
VM_ZONE="europe-west1-b"
VM_MACHINE_TYPE="e2-medium"
AUTO_APPROVE=false
SKIP_DISABLE=false
SKIP_VM=false
CLEAN=false
GITHUB_OWNER=""
INFRACOST_API_KEY=""

usage() {
  cat <<EOF
Usage: $0 --seed-project-id=PROJECT_ID --org-id=ORG_ID [OPTIONS]

Required:
  --seed-project-id=ID   GCP project ID for the Cloud Seed system
  --org-id=ID            GCP organization ID (numeric)

Options:
  --billing-account=ID   Billing account ID to link (auto-detected if omitted)
  --vm-zone=ZONE         GCP zone for the seed VM (default: europe-west1-b)
  --vm-machine-type=TYPE Machine type for the VM (default: e2-medium)
  --github-owner=OWNER   GitHub account/org allowed to deploy via WIF (e.g. Gianlucaboni)
  --infracost-api-key=KEY  Infracost API key for real cost estimation (optional)
  --auto-approve         Skip terraform apply confirmation prompt
  --skip-disable         Do not disable the Installer SA (for development only)
  --skip-vm              Do not create the seed VM (SA hierarchy only)
  --clean                Delete existing Cloud Seed resources before bootstrap (safe re-run)
  --help                 Show this help message

Example:
  $0 --seed-project-id=my-cloud-seed --org-id=123456789012 --github-owner=MyGitHubOrg
  $0 --seed-project-id=my-cloud-seed --org-id=123456789012 --github-owner=MyGitHubOrg --clean
EOF
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    --seed-project-id=*)
      SEED_PROJECT_ID="${arg#*=}"
      ;;
    --org-id=*)
      ORG_ID="${arg#*=}"
      ;;
    --billing-account=*)
      BILLING_ACCOUNT_ID="${arg#*=}"
      ;;
    --vm-zone=*)
      VM_ZONE="${arg#*=}"
      ;;
    --vm-machine-type=*)
      VM_MACHINE_TYPE="${arg#*=}"
      ;;
    --auto-approve)
      AUTO_APPROVE=true
      ;;
    --skip-disable)
      SKIP_DISABLE=true
      ;;
    --skip-vm)
      SKIP_VM=true
      ;;
    --github-owner=*)
      GITHUB_OWNER="${arg#*=}"
      ;;
    --infracost-api-key=*)
      INFRACOST_API_KEY="${arg#*=}"
      ;;
    --clean)
      CLEAN=true
      ;;
    --help|-h)
      usage
      ;;
    *)
      log_error "Unknown argument: $arg"
      usage
      ;;
  esac
done

if [[ -z "$SEED_PROJECT_ID" ]] || [[ -z "$ORG_ID" ]]; then
  log_error "Both --seed-project-id and --org-id are required."
  usage
fi

# ─── Resolve script directory (works even when called from elsewhere) ────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Step 1: Validate prerequisites ─────────────────────────────────────────
log_step "Step 1/7: Validating prerequisites"

# Check gcloud
if ! command -v gcloud &> /dev/null; then
  log_error "gcloud CLI not found. Install it from https://cloud.google.com/sdk/docs/install"
  exit 1
fi
log_ok "gcloud CLI found: $(gcloud version --format='value(Google Cloud SDK)' 2>/dev/null || gcloud version | head -1)"

# Check terraform
if ! command -v terraform &> /dev/null; then
  log_error "terraform not found. Install it from https://developer.hashicorp.com/terraform/downloads"
  exit 1
fi
log_ok "terraform found: $(terraform version -json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null || terraform version | head -1)"

# Check authentication
CURRENT_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null || true)
if [[ -z "$CURRENT_ACCOUNT" ]]; then
  log_error "No active gcloud authentication. Run: gcloud auth login"
  exit 1
fi
log_ok "Authenticated as: $CURRENT_ACCOUNT"

# Create project if it doesn't exist, otherwise verify access
if ! gcloud projects describe "$SEED_PROJECT_ID" &> /dev/null; then
  log_info "Project '$SEED_PROJECT_ID' not found — creating it..."
  if ! gcloud projects create "$SEED_PROJECT_ID" \
      --name="Cloud Seed ${SEED_PROJECT_ID}" \
      --organization="$ORG_ID" \
      --quiet; then
    log_error "Failed to create project '$SEED_PROJECT_ID'."
    exit 1
  fi
  log_ok "Seed project created: $SEED_PROJECT_ID"
else
  log_ok "Seed project accessible: $SEED_PROJECT_ID"
fi

# Check organization access
if ! gcloud organizations describe "$ORG_ID" &> /dev/null; then
  log_warn "Cannot verify organization '$ORG_ID'. Proceeding, but deny policies may fail without org access."
fi

# ─── Step 1b: Clean org-level deny policies (optional) ──────────────────────
if [[ "$CLEAN" == true ]]; then
  log_step "Step 1b/7: Cleaning previous Cloud Seed state"

  # 1. Remove local Terraform state (leftover from a previous bootstrap run)
  for f in "$SCRIPT_DIR/terraform.tfstate" "$SCRIPT_DIR/terraform.tfstate.backup" "$SCRIPT_DIR/bootstrap.auto.tfvars"; do
    if [[ -f "$f" ]]; then
      rm -f "$f"
      log_ok "Removed: $f"
    fi
  done

  # 2. Delete GCP project-level resources (may exist from a previous partial run)
  #    Strategy: attempt delete directly (--quiet skips confirmation), ignore 404s.
  #    No "describe" calls — they are slow and can hang on new/empty projects.
  log_info "Cleaning Cloud Seed GCP resources in project '$SEED_PROJECT_ID'..."

  # Service accounts — delete directly, ignore "not found"
  for sa in cloudseed-installer cloudseed-orchestrator cloudseed-ephemeral-mgr cloudseed-sa-cleanup; do
    gcloud iam service-accounts delete "${sa}@${SEED_PROJECT_ID}.iam.gserviceaccount.com" \
      --project="$SEED_PROJECT_ID" --quiet 2>/dev/null && \
      log_ok "Deleted SA: $sa" || true
  done

  # WIF pool — gcloud soft-deletes with 30-day retention, so we undelete it
  # instead and let terraform import it into state later.
  gcloud iam workload-identity-pools undelete cloudseed-github-pool \
    --location=global --project="$SEED_PROJECT_ID" --quiet 2>/dev/null && \
    log_ok "Undeleted WIF pool: cloudseed-github-pool (was soft-deleted)" || true
  WIF_POOL_EXISTS=false
  if gcloud iam workload-identity-pools describe cloudseed-github-pool \
      --location=global --project="$SEED_PROJECT_ID" \
      --format="value(state)" 2>/dev/null | grep -qi "ACTIVE"; then
    WIF_POOL_EXISTS=true
    log_info "WIF pool exists and is active — will be imported into terraform state."
  fi

  # Custom IAM roles — delete directly, ignore "not found"
  for role in cloudSeedOrchestratorOps cloudSeedEphemeralReadOnly; do
    gcloud iam roles delete "$role" --project="$SEED_PROJECT_ID" --quiet 2>/dev/null && \
      log_ok "Deleted role: $role" || true
  done

  # Pub/Sub topic — delete directly, ignore "not found"
  gcloud pubsub topics delete cloudseed-ephemeral-sa-cleanup \
    --project="$SEED_PROJECT_ID" --quiet 2>/dev/null && \
    log_ok "Deleted Pub/Sub topic: cloudseed-ephemeral-sa-cleanup" || true

  # Cloud Scheduler job — try both region formats, ignore "not found"
  gcloud scheduler jobs delete cloudseed-ephemeral-sa-cleanup \
    --location="${VM_ZONE%-*}" --project="$SEED_PROJECT_ID" --quiet 2>/dev/null && \
    log_ok "Deleted Scheduler job: cloudseed-ephemeral-sa-cleanup" || \
  gcloud scheduler jobs delete cloudseed-ephemeral-sa-cleanup \
    --location="$VM_ZONE" --project="$SEED_PROJECT_ID" --quiet 2>/dev/null && \
    log_ok "Deleted Scheduler job: cloudseed-ephemeral-sa-cleanup" || true

  # 3. Delete deny policies (both project-level and org-level)
  # Uses IAM v2 REST API directly — gcloud CLI does not support denyPolicies kind.
  IAM_V2_BASE="https://iam.googleapis.com/v2/policies"
  ACCESS_TOKEN=$(gcloud auth print-access-token)

  # Project-level deny policies
  PROJECT_ENCODED="cloudresourcemanager.googleapis.com%2Fprojects%2F${SEED_PROJECT_ID}"
  for policy in "cloudseed-deny-modify-critical-sas" "cloudseed-deny-seed-iam-modification"; do
    log_info "Deleting project-level deny policy: $policy"
    HTTP_CODE=$(curl -s -o /tmp/deny_policy_delete.json -w "%{http_code}" -X DELETE \
      -H "Authorization: Bearer ${ACCESS_TOKEN}" \
      "${IAM_V2_BASE}/${PROJECT_ENCODED}/denypolicies/${policy}")

    if [[ "$HTTP_CODE" == "200" ]]; then
      log_ok "Deleted: $policy"
    elif [[ "$HTTP_CODE" == "404" ]]; then
      log_warn "Policy '$policy' not found — skipping."
    else
      log_error "Failed to delete '$policy' (HTTP $HTTP_CODE): $(cat /tmp/deny_policy_delete.json)"
      exit 1
    fi
  done

  # Org-level deny policies
  ORG_ENCODED="cloudresourcemanager.googleapis.com%2Forganizations%2F${ORG_ID}"
  for policy in "cloudseed-deny-project-deletion" "cloudseed-deny-cross-project-secrets"; do
    log_info "Deleting org-level deny policy: $policy"
    HTTP_CODE=$(curl -s -o /tmp/deny_policy_delete.json -w "%{http_code}" -X DELETE \
      -H "Authorization: Bearer ${ACCESS_TOKEN}" \
      "${IAM_V2_BASE}/${ORG_ENCODED}/denypolicies/${policy}")

    if [[ "$HTTP_CODE" == "200" ]]; then
      log_ok "Deleted: $policy"
    elif [[ "$HTTP_CODE" == "404" ]]; then
      log_warn "Policy '$policy' not found — skipping."
    else
      log_error "Failed to delete '$policy' (HTTP $HTTP_CODE): $(cat /tmp/deny_policy_delete.json)"
      exit 1
    fi
  done
  rm -f /tmp/deny_policy_delete.json
fi

# ─── Step 2: Enable required APIs ───────────────────────────────────────────
log_step "Step 2/7: Enabling required GCP APIs"

# Auto-detect billing account if not provided
if [[ -z "$BILLING_ACCOUNT_ID" ]]; then
  BILLING_ACCOUNT_ID=$(gcloud billing accounts list --filter=open=true --format="value(ACCOUNT_ID)" --limit=1 2>/dev/null || true)
  if [[ -n "$BILLING_ACCOUNT_ID" ]]; then
    log_ok "Auto-detected billing account: $BILLING_ACCOUNT_ID"
  else
    log_warn "No billing account found. Project creation and API enablement may fail."
  fi
fi

# Link billing to seed project (required before enabling most APIs)
if [[ -n "$BILLING_ACCOUNT_ID" ]]; then
  gcloud billing projects link "$SEED_PROJECT_ID" \
    --billing-account="$BILLING_ACCOUNT_ID" --quiet 2>/dev/null && \
    log_ok "Billing account linked to seed project" || \
    log_warn "Could not link billing (may already be linked)"
fi

REQUIRED_APIS=(
  "iam.googleapis.com"
  "cloudresourcemanager.googleapis.com"
  "sts.googleapis.com"
  "iamcredentials.googleapis.com"
  "cloudscheduler.googleapis.com"
  "pubsub.googleapis.com"
  "serviceusage.googleapis.com"
  "compute.googleapis.com"
  "cloudbilling.googleapis.com"
  "run.googleapis.com"
  "artifactregistry.googleapis.com"
  "cloudbuild.googleapis.com"
  "sqladmin.googleapis.com"
  "bigquery.googleapis.com"
  "storage.googleapis.com"
)

for api in "${REQUIRED_APIS[@]}"; do
  log_info "Enabling $api..."
  gcloud services enable "$api" --project="$SEED_PROJECT_ID" --quiet 2>/dev/null || {
    log_warn "Could not enable $api — it may already be enabled or require manual activation."
  }
done
log_ok "Required APIs enabled"

# Disable GCP default service accounts (overly broad permissions)
PROJECT_NUMBER=$(gcloud projects describe "$SEED_PROJECT_ID" --format="value(projectNumber)" 2>/dev/null)
if [[ -n "$PROJECT_NUMBER" ]]; then
  DEFAULT_COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
  if gcloud iam service-accounts describe "$DEFAULT_COMPUTE_SA" --project="$SEED_PROJECT_ID" &>/dev/null; then
    gcloud iam service-accounts disable "$DEFAULT_COMPUTE_SA" --project="$SEED_PROJECT_ID" --quiet 2>/dev/null && \
      log_ok "Disabled default Compute Engine SA: $DEFAULT_COMPUTE_SA" || \
      log_warn "Could not disable default Compute SA (may already be disabled)"
  fi
fi

# ─── Step 3: Terraform init ─────────────────────────────────────────────────
log_step "Step 3/7: Initializing Terraform"

cd "$SCRIPT_DIR"
terraform init -input=false
log_ok "Terraform initialized"

# Import WIF pool if it survived from a previous run (soft-delete retention)
if [[ "$CLEAN" == true ]] && [[ "$WIF_POOL_EXISTS" == true ]]; then
  log_info "Importing existing WIF pool into terraform state..."
  terraform import \
    -var="seed_project_id=$SEED_PROJECT_ID" \
    -var="org_id=$ORG_ID" \
    google_iam_workload_identity_pool.github \
    "projects/$SEED_PROJECT_ID/locations/global/workloadIdentityPools/cloudseed-github-pool" \
    2>/dev/null && \
    log_ok "WIF pool imported into state" || \
    log_warn "WIF pool import skipped (may already be in state)"
fi

# ─── Step 4: Terraform plan + apply ─────────────────────────────────────────
log_step "Step 4/7: Planning and applying SA hierarchy"

# Write tfvars for this run
cat > "$SCRIPT_DIR/bootstrap.auto.tfvars" <<EOF
seed_project_id    = "$SEED_PROJECT_ID"
org_id             = "$ORG_ID"
billing_account_id = "$BILLING_ACCOUNT_ID"
EOF
log_info "Wrote bootstrap.auto.tfvars"

# Plan
log_info "Running terraform plan..."
terraform plan \
  -input=false \
  -out=bootstrap.tfplan

log_ok "Plan complete"

# Apply
if [[ "$AUTO_APPROVE" == true ]]; then
  log_info "Running terraform apply (auto-approved)..."
  terraform apply -input=false bootstrap.tfplan
else
  log_info "Running terraform apply..."
  terraform apply bootstrap.tfplan
fi

log_ok "Terraform apply complete — SA hierarchy created"

# Clean up plan file
rm -f bootstrap.tfplan

# ─── Step 5: Grant billing.user to Orchestrator SA ────────────────────────
log_step "Step 5/7: Granting billing access to Orchestrator SA"

ORCHESTRATOR_SA_EMAIL=$(terraform output -raw orchestrator_sa_email 2>/dev/null)

if [[ -n "$BILLING_ACCOUNT_ID" ]] && [[ -n "$ORCHESTRATOR_SA_EMAIL" ]]; then
  log_info "Granting roles/billing.user on billing account $BILLING_ACCOUNT_ID"
  gcloud billing accounts add-iam-policy-binding "$BILLING_ACCOUNT_ID" \
    --member="serviceAccount:$ORCHESTRATOR_SA_EMAIL" \
    --role="roles/billing.user" \
    --quiet 2>/dev/null && \
    log_ok "Billing access granted to Orchestrator SA" || \
    log_warn "Could not grant billing access. You may need to run manually:
  gcloud billing accounts add-iam-policy-binding $BILLING_ACCOUNT_ID \\
    --member=\"serviceAccount:$ORCHESTRATOR_SA_EMAIL\" \\
    --role=\"roles/billing.user\""
else
  log_warn "Skipping billing binding (no billing account or orchestrator SA found)."
  log_warn "The Orchestrator won't be able to link billing to new projects."
fi

# ─── Step 6: Disable the Installer SA ───────────────────────────────────────
log_step "Step 6/7: Disabling Installer SA"

INSTALLER_SA_EMAIL=$(terraform output -raw installer_sa_email 2>/dev/null)

if [[ -z "$INSTALLER_SA_EMAIL" ]]; then
  log_error "Could not retrieve Installer SA email from Terraform output."
  log_error "The SA hierarchy was created but the Installer SA was NOT disabled."
  log_error "Manually disable it with: gcloud iam service-accounts disable <SA_EMAIL>"
  exit 1
fi

if [[ "$SKIP_DISABLE" == true ]]; then
  log_warn "Skipping Installer SA disable (--skip-disable flag set)."
  log_warn "THIS IS FOR DEVELOPMENT ONLY. In production, the Installer SA must be disabled."
else
  log_info "Disabling Installer SA: $INSTALLER_SA_EMAIL"
  gcloud iam service-accounts disable "$INSTALLER_SA_EMAIL" \
    --project="$SEED_PROJECT_ID" \
    --quiet

  log_ok "Installer SA disabled: $INSTALLER_SA_EMAIL"
  log_info "The Installer SA is now permanently disabled."
  log_info "To re-enable (emergency only): gcloud iam service-accounts enable $INSTALLER_SA_EMAIL"
fi

# ─── Step 7: Create seed VM ──────────────────────────────────────────────────
if [[ "$SKIP_VM" == true ]]; then
  log_warn "Skipping VM creation (--skip-vm flag set)."
else
  log_step "Step 7/7: Creating seed VM with Orchestrator SA"

  # Re-read in case it wasn't set earlier (e.g. billing step was skipped)
  ORCHESTRATOR_SA_EMAIL=$(terraform output -raw orchestrator_sa_email 2>/dev/null)

  if [[ -z "$ORCHESTRATOR_SA_EMAIL" ]]; then
    log_error "Could not retrieve Orchestrator SA email. Skipping VM creation."
  else
    # Check if VM already exists
    if gcloud compute instances describe cloud-seed-vm \
        --zone="$VM_ZONE" --project="$SEED_PROJECT_ID" &>/dev/null; then
      log_warn "VM 'cloud-seed-vm' already exists in $VM_ZONE. Skipping creation."
    else
      log_info "Creating VM with SA: $ORCHESTRATOR_SA_EMAIL"

      gcloud compute instances create cloud-seed-vm \
        --project="$SEED_PROJECT_ID" \
        --zone="$VM_ZONE" \
        --machine-type="$VM_MACHINE_TYPE" \
        --image-family=debian-12 \
        --image-project=debian-cloud \
        --boot-disk-size=30GB \
        --service-account="$ORCHESTRATOR_SA_EMAIL" \
        --scopes=cloud-platform \
        --tags=cloud-seed \
        --metadata-from-file=startup-script="$SCRIPT_DIR/vm-startup.sh" \
        --metadata=github-owner="${GITHUB_OWNER}",infracost-api-key="${INFRACOST_API_KEY}" \
        --quiet

      log_ok "VM 'cloud-seed-vm' created in $VM_ZONE"
      log_info "The VM is booting and running the startup script."
      log_info "It will install Docker, clone the repo, and start docker-compose."
      log_info "This takes ~5 minutes. Check progress with:"
      log_info "  gcloud compute ssh cloud-seed-vm --zone=$VM_ZONE --project=$SEED_PROJECT_ID -- tail -f /var/log/cloud-seed-startup.log"
    fi

    # Ensure SSH firewall rule exists
    if ! gcloud compute firewall-rules describe allow-ssh \
        --project="$SEED_PROJECT_ID" &>/dev/null; then
      gcloud compute firewall-rules create allow-ssh \
        --project="$SEED_PROJECT_ID" \
        --allow=tcp:22 \
        --target-tags=cloud-seed \
        --quiet
      log_ok "Firewall rule 'allow-ssh' created"
    fi
  fi
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
log_ok "Cloud Seed MCP Bootstrap Complete"
echo ""
echo "  Service Accounts created:"
echo "    Installer (DISABLED): $INSTALLER_SA_EMAIL"
echo "    Orchestrator:         $(terraform output -raw orchestrator_sa_email 2>/dev/null)"
echo "    Ephemeral Pool Mgr:   $(terraform output -raw ephemeral_sa_pool_email 2>/dev/null)"
echo ""
echo "  Next steps:"
echo "    1. Wait for VM startup (~5 min), then connect via SSH tunnel:"
echo "       gcloud compute ssh cloud-seed-vm --zone=$VM_ZONE --project=$SEED_PROJECT_ID -- -L 8000:localhost:8000 -N"
echo "    2. Configure Claude Desktop to connect to http://localhost:8000/mcp"
echo "    3. Ask Claude to create your first project!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
