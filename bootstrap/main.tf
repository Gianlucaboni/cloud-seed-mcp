###############################################################################
# main.tf — Root module for Cloud Seed MCP bootstrap
#
# Orchestrates the 4-level Service Account hierarchy:
#   1. SA Installer  — one-time bootstrap, disabled after use
#   2. SA Orchestrator — persistent, operates across all client projects
#   3. SA per-Project — one set of 3 SAs per client project
#   4. SA Ephemeral  — dynamic, short-lived SAs for Tool Forge sandbox
#
# See CLAUDE.md "Service Account Hierarchy — 4 Levels" for full context.
###############################################################################

# ─────────────────────────────────────────────────────────────────────────────
# Enable required APIs on the seed project
# ─────────────────────────────────────────────────────────────────────────────
resource "google_project_service" "required_apis" {
  for_each = toset([
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "sts.googleapis.com",                 # For Workload Identity Federation
    "iamcredentials.googleapis.com",      # For SA token generation
    "cloudscheduler.googleapis.com",      # For ephemeral SA TTL cleanup
    "run.googleapis.com",                 # For Cloud Run management
    "artifactregistry.googleapis.com",    # For container image management
    "cloudbuild.googleapis.com",          # For CI/CD
    "sqladmin.googleapis.com",            # For Cloud SQL management
    "bigquery.googleapis.com",            # For BigQuery management
    "storage.googleapis.com",             # For GCS management
    "serviceusage.googleapis.com",        # For API management
    "compute.googleapis.com",             # For VM management
    "cloudbilling.googleapis.com",        # For billing management
  ])

  project = var.seed_project_id
  service = each.value

  disable_dependent_services = false
  disable_on_destroy         = false
}

# =============================================================================
# Workload Identity Federation — GitHub Actions pool
# =============================================================================

resource "google_iam_workload_identity_pool" "github" {
  provider                  = google-beta
  workload_identity_pool_id = "cloudseed-github-pool"
  display_name              = "Cloud Seed GitHub Pool"
  description               = "WIF pool for GitHub Actions CI/CD across all client projects"
  project                   = var.seed_project_id
  disabled                  = false

  depends_on = [google_project_service.required_apis]
}

# ─────────────────────────────────────────────────────────────────────────────
# Per-Project SA module — creates Runtime, Deploy, Data SAs for each client
# ─────────────────────────────────────────────────────────────────────────────
module "project_sa" {
  source   = "./modules/project_sa"
  for_each = var.client_projects

  project_name    = each.key
  project_id      = each.value.project_id
  seed_project_id = var.seed_project_id
  labels          = var.seed_labels

  github_access = each.value.github_access
  wif_pool_name = google_iam_workload_identity_pool.github.name
  wif_pool_id   = "cloudseed-github-pool"
}

# ─────────────────────────────────────────────────────────────────────────────
# Ephemeral SA module — provides the Tool Forge sandbox SA factory
# ─────────────────────────────────────────────────────────────────────────────
module "ephemeral_sa" {
  source = "./modules/ephemeral_sa"

  seed_project_id = var.seed_project_id
  default_region  = var.default_region
  labels          = var.seed_labels

  depends_on = [
    google_project_service.required_apis,
  ]
}
