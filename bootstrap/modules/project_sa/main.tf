###############################################################################
# modules/project_sa/main.tf — Per-Project Service Accounts
#
# Creates 3 SAs per client project with structural isolation:
#   - SA Runtime: Used by Cloud Run services and VMs (minimal operation perms)
#   - SA Deploy:  Pushes images and deploys (no infrastructure access)
#   - SA Data:    Read/write on buckets and databases (no infrastructure access)
#
# All SAs are created in the SEED project but granted permissions only in
# their target client project. This ensures cross-project isolation: an
# IoT project SA cannot see Analytics project resources.
###############################################################################

locals {
  # Truncate project name to fit within the 30-char SA account_id limit
  # Format: cs-{name}-{role} where cs=cloudseed prefix
  sa_prefix = "cs-${substr(var.project_name, 0, 16)}"
}

# =============================================================================
# SA RUNTIME — Minimal Cloud Run / VM operation permissions
# =============================================================================

resource "google_service_account" "runtime" {
  account_id   = "${local.sa_prefix}-runtime"
  display_name = "Cloud Seed — ${var.project_name} Runtime"
  description  = "Runtime SA for Cloud Run services and VMs in project ${var.project_name}. Minimal operational permissions."
  project      = var.seed_project_id
}

# Runtime SA: invoke Cloud Run services
resource "google_project_iam_member" "runtime_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Runtime SA: write logs
resource "google_project_iam_member" "runtime_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Runtime SA: write metrics
resource "google_project_iam_member" "runtime_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Runtime SA: write traces
resource "google_project_iam_member" "runtime_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Runtime SA: additional roles (if any)
resource "google_project_iam_member" "runtime_additional" {
  for_each = toset(var.runtime_additional_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# =============================================================================
# SA DEPLOY — Image push + deployment, NO infrastructure access
# =============================================================================

resource "google_service_account" "deploy" {
  account_id   = "${local.sa_prefix}-deploy"
  display_name = "Cloud Seed — ${var.project_name} Deploy"
  description  = "Deploy SA for project ${var.project_name}. Can push images and deploy to Cloud Run. No infrastructure permissions."
  project      = var.seed_project_id
}

# Deploy SA: manage Cloud Run services (create, update, delete services)
resource "google_project_iam_member" "deploy_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Deploy SA: push container images to Artifact Registry
resource "google_project_iam_member" "deploy_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Deploy SA: read Cloud Build logs (needed for deployment tracking)
resource "google_project_iam_member" "deploy_build_viewer" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.viewer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Deploy SA: act as the Runtime SA when deploying Cloud Run services
# SA-level binding (targeted: only this specific Runtime SA)
resource "google_service_account_iam_member" "deploy_acts_as_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

# Deploy SA: project-level serviceAccountUser on client project
# Required for Cloud Run to accept cross-project SA as service identity
resource "google_project_iam_member" "deploy_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Deploy SA: additional roles (if any)
resource "google_project_iam_member" "deploy_additional" {
  for_each = toset(var.deploy_additional_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# =============================================================================
# SA DATA — Read/write on buckets and databases, NO infrastructure access
# =============================================================================

resource "google_service_account" "data" {
  account_id   = "${local.sa_prefix}-data"
  display_name = "Cloud Seed — ${var.project_name} Data"
  description  = "Data SA for project ${var.project_name}. Read/write on buckets and databases. No infrastructure permissions."
  project      = var.seed_project_id
}

# Data SA: BigQuery data read/write
resource "google_project_iam_member" "data_bigquery_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.data.email}"
}

# Data SA: BigQuery job execution (required to run queries)
resource "google_project_iam_member" "data_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.data.email}"
}

# Data SA: GCS object read/write
resource "google_project_iam_member" "data_storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.data.email}"
}

# Data SA: Cloud SQL client (connect to instances, not manage them)
resource "google_project_iam_member" "data_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.data.email}"
}

# Data SA: Firestore read/write
resource "google_project_iam_member" "data_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.data.email}"
}

# Data SA: additional roles (if any)
resource "google_project_iam_member" "data_additional" {
  for_each = toset(var.data_additional_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.data.email}"
}

# =============================================================================
# WIF: GitHub Actions OIDC Provider + SA Deploy Binding
# =============================================================================
# Enables GitHub Actions in the specified repo to authenticate as SA Deploy
# via Workload Identity Federation. No SA keys needed.

locals {
  # Build a map keyed by "owner-<value>" or "repo-<owner>-<repo>" for for_each
  github_access_map = {
    for access in var.github_access :
    "${access.type}-${replace(lower(access.value), "/", "-")}" => access
  }
}

resource "google_iam_workload_identity_pool_provider" "github" {
  for_each = local.github_access_map

  provider                           = google-beta
  project                            = var.seed_project_id
  workload_identity_pool_id          = var.wif_pool_id
  workload_identity_pool_provider_id = "${local.sa_prefix}-${substr(md5(each.key), 0, 8)}"
  display_name                       = substr("GH ${var.project_name} ${each.value.value}", 0, 32)
  description                        = each.value.type == "owner" ? "OIDC for all repos owned by ${each.value.value}" : "OIDC for repo ${each.value.value}"

  attribute_mapping = {
    "google.subject"              = "assertion.sub"
    "attribute.actor"             = "assertion.actor"
    "attribute.repository"        = "assertion.repository"
    "attribute.repository_owner"  = "assertion.repository_owner"
  }

  attribute_condition = each.value.type == "owner" ? "attribute.repository_owner == '${each.value.value}'" : "attribute.repository == '${each.value.value}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deploy_wif_binding" {
  for_each = local.github_access_map

  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = each.value.type == "owner" ? "principalSet://iam.googleapis.com/${var.wif_pool_name}/attribute.repository_owner/${each.value.value}" : "principalSet://iam.googleapis.com/${var.wif_pool_name}/attribute.repository/${each.value.value}"
}
