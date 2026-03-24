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
  --auto-approve         Skip terraform apply confirmation prompt
  --skip-disable         Do not disable the Installer SA (for development only)
  --skip-vm              Do not create the seed VM (SA hierarchy only)
  --help                 Show this help message

Example:
  $0 --seed-project-id=my-cloud-seed --org-id=123456789012
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
log_step "Step 1/5: Validating prerequisites"

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

# Check project exists and is accessible
if ! gcloud projects describe "$SEED_PROJECT_ID" &> /dev/null; then
  log_error "Cannot access project '$SEED_PROJECT_ID'. Verify it exists and you have access."
  exit 1
fi
log_ok "Seed project accessible: $SEED_PROJECT_ID"

# Check organization access
if ! gcloud organizations describe "$ORG_ID" &> /dev/null; then
  log_warn "Cannot verify organization '$ORG_ID'. Proceeding, but deny policies may fail without org access."
fi

# ─── Step 2: Enable required APIs ───────────────────────────────────────────
log_step "Step 2/6: Enabling required GCP APIs"

# Auto-detect billing account if not provided
if [[ -z "$BILLING_ACCOUNT_ID" ]]; then
  BILLING_ACCOUNT_ID=$(gcloud billing accounts list --filter=open=true --format="value(ACCOUNT_ID)" --limit=1 2>/dev/null || true)
  if [[ -n "$BILLING_ACCOUNT_ID" ]]; then
    log_ok "Auto-detected billing account: $BILLING_ACCOUNT_ID"
  else
    log_warn "No billing account found. Project creation and API enablement may fail."
  fi
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

# ─── Step 3: Terraform init ─────────────────────────────────────────────────
log_step "Step 3/6: Initializing Terraform"

cd "$SCRIPT_DIR"
terraform init -input=false
log_ok "Terraform initialized"

# ─── Step 4: Terraform plan + apply ─────────────────────────────────────────
log_step "Step 4/6: Planning and applying SA hierarchy"

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

# ─── Step 5: Disable the Installer SA ───────────────────────────────────────
log_step "Step 5/6: Disabling Installer SA"

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

# ─── Step 6: Create seed VM ──────────────────────────────────────────────────
if [[ "$SKIP_VM" == true ]]; then
  log_warn "Skipping VM creation (--skip-vm flag set)."
else
  log_step "Step 6/6: Creating seed VM with Orchestrator SA"

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
