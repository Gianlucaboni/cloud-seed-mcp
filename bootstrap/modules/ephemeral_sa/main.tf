###############################################################################
# modules/ephemeral_sa/main.tf — Ephemeral SA for Tool Forge Sandbox
#
# Provides infrastructure for creating short-lived, read-only SAs used by
# the Tool Forge to test auto-generated tools in a sandbox environment.
#
# Architecture:
#   - A "pool manager" SA has permission to create/delete ephemeral SAs
#   - A Cloud Scheduler job runs periodically to clean up expired SAs
#   - A Cloud Function (deployed separately) handles the actual cleanup
#   - Ephemeral SAs are labeled with creation time for TTL enforcement
#
# The actual creation of individual ephemeral SAs happens at runtime via
# the Tool Forge, not at bootstrap time. This module sets up the
# infrastructure to support that pattern.
###############################################################################

# =============================================================================
# Pool Manager SA — creates and manages ephemeral SAs
# =============================================================================
# This SA is used by the Tool Forge to create ephemeral SAs on demand.
# It has permission to create SAs and grant them read-only roles.

resource "google_service_account" "pool_manager" {
  account_id   = "cloudseed-ephemeral-mgr"
  display_name = "Cloud Seed — Ephemeral SA Pool Manager"
  description  = "Manages creation and cleanup of ephemeral SAs for Tool Forge sandbox testing."
  project      = var.seed_project_id
}

# Pool manager can create and delete service accounts (ephemeral SAs only,
# deny policies on sa_hierarchy.tf protect the critical SAs)
resource "google_project_iam_member" "pool_manager_sa_admin" {
  project = var.seed_project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.pool_manager.email}"
}

# Pool manager can bind IAM roles on projects (to grant read-only access)
resource "google_project_iam_member" "pool_manager_project_iam" {
  project = var.seed_project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${google_service_account.pool_manager.email}"
}

# =============================================================================
# Custom role for ephemeral SAs — read-only on target projects
# =============================================================================
# This is the role that gets assigned to each ephemeral SA on the target
# project. Strictly read-only: list and get, no create/update/delete.

resource "google_project_iam_custom_role" "ephemeral_readonly" {
  role_id     = "cloudSeedEphemeralReadOnly"
  title       = "Cloud Seed Ephemeral Read-Only"
  description = "Read-only permissions for Tool Forge sandbox testing. Assigned to ephemeral SAs."
  project     = var.seed_project_id

  permissions = [
    # Compute (read-only)
    "compute.instances.get",
    "compute.instances.list",
    "compute.networks.get",
    "compute.networks.list",
    "compute.subnetworks.get",
    "compute.subnetworks.list",
    "compute.firewalls.get",
    "compute.firewalls.list",

    # Cloud Run (read-only)
    "run.services.get",
    "run.services.list",
    "run.revisions.get",
    "run.revisions.list",

    # Storage (read-only)
    "storage.buckets.get",
    "storage.buckets.list",
    "storage.objects.get",
    "storage.objects.list",

    # BigQuery (read-only)
    "bigquery.datasets.get",
    "bigquery.tables.get",
    "bigquery.tables.list",

    # Cloud SQL (read-only)
    "cloudsql.instances.get",
    "cloudsql.instances.list",

    # Firestore (read-only)
    "datastore.entities.get",
    "datastore.entities.list",

    # IAM (read-only, to inspect configuration)
    "iam.serviceAccounts.list",
    "iam.serviceAccounts.get",

    # Resource Manager (read-only)
    "resourcemanager.projects.get",
  ]
}

# =============================================================================
# Cleanup infrastructure — Cloud Scheduler + Cloud Function
# =============================================================================
# A Cloud Scheduler job triggers periodically to clean up ephemeral SAs
# that have exceeded their TTL. The actual cleanup logic is in a Cloud
# Function (deployed separately by the core-mcp system).

# Pub/Sub topic for cleanup triggers
resource "google_pubsub_topic" "ephemeral_cleanup" {
  name    = "cloudseed-ephemeral-sa-cleanup"
  project = var.seed_project_id

  labels = var.labels
}

# SA for the cleanup Cloud Function
resource "google_service_account" "cleanup_function" {
  account_id   = "cloudseed-sa-cleanup"
  display_name = "Cloud Seed — Ephemeral SA Cleanup Function"
  description  = "Runs the periodic cleanup of expired ephemeral SAs."
  project      = var.seed_project_id
}

# Cleanup function needs to list and delete SAs
resource "google_project_iam_member" "cleanup_sa_admin" {
  project = var.seed_project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.cleanup_function.email}"
}

# Cleanup function needs to remove IAM bindings of expired SAs from projects
resource "google_project_iam_member" "cleanup_project_iam" {
  project = var.seed_project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${google_service_account.cleanup_function.email}"
}

# Cloud Scheduler job to trigger cleanup
resource "google_cloud_scheduler_job" "ephemeral_cleanup" {
  name        = "cloudseed-ephemeral-sa-cleanup"
  description = "Periodically cleans up expired ephemeral SAs (TTL: ${var.ttl_hours}h)"
  project     = var.seed_project_id
  region      = var.default_region
  schedule    = var.cleanup_schedule
  time_zone   = "UTC"

  pubsub_target {
    topic_name = google_pubsub_topic.ephemeral_cleanup.id
    data = base64encode(jsonencode({
      action               = "cleanup"
      ttl_hours            = var.ttl_hours
      seed_project_id      = var.seed_project_id
      sa_prefix            = "cloudseed-eph-"
      max_concurrent       = var.max_concurrent_ephemeral_sas
      readonly_custom_role = google_project_iam_custom_role.ephemeral_readonly.id
    }))
  }

  retry_config {
    retry_count          = 3
    min_backoff_duration = "10s"
    max_backoff_duration = "300s"
  }
}
