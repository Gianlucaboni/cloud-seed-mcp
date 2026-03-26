###############################################################################
# sa_hierarchy.tf — SA Installer + SA Orchestrator
#
# Level 1: SA Installer — used only during bootstrap, then disabled
# Level 2: SA Orchestrator — persistent, manages all client projects
###############################################################################

# =============================================================================
# LEVEL 1: SA INSTALLER
# =============================================================================
# Used exclusively during the bootstrap phase to create all other SAs and
# configure base IAM policies. Disabled (not deleted) immediately after
# bootstrap completes — see install.sh for the disable step.
# =============================================================================

resource "google_service_account" "installer" {
  account_id   = "cloudseed-installer"
  display_name = "Cloud Seed MCP — Installer (bootstrap only)"
  description  = "One-time bootstrap SA. Creates other SAs and configures IAM. Disabled after installation."
  project      = var.seed_project_id
}

# Installer needs to create and manage other service accounts
resource "google_project_iam_member" "installer_sa_admin" {
  project = var.seed_project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.installer.email}"
}

# Installer needs to set IAM policies (security admin for deny policies, org-level)
resource "google_project_iam_member" "installer_security_admin" {
  project = var.seed_project_id
  role    = "roles/iam.securityAdmin"
  member  = "serviceAccount:${google_service_account.installer.email}"
}

# Installer needs to bind IAM roles on projects
resource "google_project_iam_member" "installer_project_iam_admin" {
  project = var.seed_project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${google_service_account.installer.email}"
}

# Installer needs to enable APIs
resource "google_project_iam_member" "installer_service_usage_admin" {
  project = var.seed_project_id
  role    = "roles/serviceusage.serviceUsageAdmin"
  member  = "serviceAccount:${google_service_account.installer.email}"
}

# =============================================================================
# LEVEL 2: SA ORCHESTRATOR
# =============================================================================
# Persistent SA that lives in the seed project and operates on all client
# projects via Terraform + OPA validation. Has explicit deny policies on
# destructive operations (see deny_policy.tf).
# =============================================================================

resource "google_service_account" "orchestrator" {
  account_id   = "cloudseed-orchestrator"
  display_name = "Cloud Seed MCP — Orchestrator"
  description  = "Core MCP orchestrator. Manages client projects via Terraform with OPA validation."
  project      = var.seed_project_id
}

# ─── Orchestrator permissions on the SEED project ────────────────────────────

# Orchestrator can create and manage per-project SAs in the seed project
resource "google_project_iam_member" "orchestrator_sa_creator" {
  project = var.seed_project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Orchestrator can view IAM policies (needed for terraform plan)
resource "google_project_iam_member" "orchestrator_iam_viewer" {
  project = var.seed_project_id
  role    = "roles/iam.securityReviewer"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Orchestrator can bind IAM roles on the seed project
# (needed to assign roles to per-project SAs created here)
resource "google_project_iam_member" "orchestrator_seed_iam_admin" {
  project = var.seed_project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Orchestrator can manage Cloud Scheduler (for ephemeral SA TTL)
resource "google_project_iam_member" "orchestrator_scheduler_admin" {
  project = var.seed_project_id
  role    = "roles/cloudscheduler.admin"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

# ─── Orchestrator permissions at ORGANIZATION level ──────────────────────────

# Orchestrator can create new projects under the organization
resource "google_organization_iam_member" "orchestrator_project_creator" {
  org_id = var.org_id
  role   = "roles/resourcemanager.projectCreator"
  member = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Orchestrator can link billing to new projects
resource "google_organization_iam_member" "orchestrator_billing_user" {
  org_id = var.org_id
  role   = "roles/billing.user"
  member = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Orchestrator can enable APIs on new projects (before client_projects is populated)
resource "google_organization_iam_member" "orchestrator_service_usage" {
  org_id = var.org_id
  role   = "roles/serviceusage.serviceUsageAdmin"
  member = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Orchestrator can set IAM policies on new projects (before client_projects is populated)
resource "google_organization_iam_member" "orchestrator_project_iam_admin" {
  org_id = var.org_id
  role   = "roles/resourcemanager.projectIamAdmin"
  member = "serviceAccount:${google_service_account.orchestrator.email}"
}

# ─── Orchestrator permissions on CLIENT projects ─────────────────────────────
# Applied per client project via for_each

resource "google_project_iam_member" "orchestrator_client_editor" {
  for_each = var.client_projects

  project = each.value.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Orchestrator can manage IAM on client projects (to bind per-project SAs)
resource "google_project_iam_member" "orchestrator_client_iam_admin" {
  for_each = var.client_projects

  project = each.value.project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Orchestrator can manage service accounts in client projects
resource "google_project_iam_member" "orchestrator_client_sa_admin" {
  for_each = var.client_projects

  project = each.value.project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

# Orchestrator can enable APIs in client projects
resource "google_project_iam_member" "orchestrator_client_service_usage" {
  for_each = var.client_projects

  project = each.value.project_id
  role    = "roles/serviceusage.serviceUsageAdmin"
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}

# ─── Custom role: Orchestrator operational permissions ───────────────────────
# Scoped to what the orchestrator actually needs day-to-day on the seed project

resource "google_project_iam_custom_role" "orchestrator_ops" {
  role_id     = "cloudSeedOrchestratorOps"
  title       = "Cloud Seed Orchestrator Operations"
  description = "Operational permissions for the Cloud Seed orchestrator on the seed project"
  project     = var.seed_project_id

  permissions = [
    # Cloud Run management
    "run.services.create",
    "run.services.update",
    "run.services.get",
    "run.services.list",
    "run.services.getIamPolicy",
    "run.services.setIamPolicy",

    # Artifact Registry
    "artifactregistry.repositories.create",
    "artifactregistry.repositories.get",
    "artifactregistry.repositories.list",

    # Storage (for Terraform state, artifacts)
    "storage.buckets.create",
    "storage.buckets.get",
    "storage.buckets.list",
    "storage.objects.create",
    "storage.objects.get",
    "storage.objects.list",
    "storage.objects.update",
    "storage.objects.delete",

    # Compute (read-only for state verification)
    "compute.instances.list",
    "compute.instances.get",
    "compute.zones.list",
    "compute.regions.list",

    # Resource manager (read)
    "resourcemanager.projects.get",
  ]
}

resource "google_project_iam_member" "orchestrator_custom_ops" {
  project = var.seed_project_id
  role    = google_project_iam_custom_role.orchestrator_ops.id
  member  = "serviceAccount:${google_service_account.orchestrator.email}"
}
