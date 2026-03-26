###############################################################################
# main.tf — Per-project SA provisioning (run by Orchestrator)
#
# This root module manages:
#   - Per-project SAs: Runtime, Deploy, Data
#   - Orchestrator permissions on each client project
#   - WIF providers for GitHub CI/CD
#
# The Orchestrator uses org-level projectIamAdmin to bootstrap its own
# editor + IAM admin roles on each new client project, then uses those
# to grant fine-grained permissions to the per-project SAs.
###############################################################################

# ─── Orchestrator permissions on client projects ─────────────────────────────
# These must be in the projects module (not bootstrap sa_hierarchy.tf) because
# new projects don't exist at bootstrap time.

locals {
  orchestrator_email = "cloudseed-orchestrator@${var.seed_project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "orchestrator_client_editor" {
  for_each = var.client_projects

  project = each.value.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${local.orchestrator_email}"
}

resource "google_project_iam_member" "orchestrator_client_iam_admin" {
  for_each = var.client_projects

  project = each.value.project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${local.orchestrator_email}"
}

resource "google_project_iam_member" "orchestrator_client_sa_admin" {
  for_each = var.client_projects

  project = each.value.project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${local.orchestrator_email}"
}

resource "google_project_iam_member" "orchestrator_client_service_usage" {
  for_each = var.client_projects

  project = each.value.project_id
  role    = "roles/serviceusage.serviceUsageAdmin"
  member  = "serviceAccount:${local.orchestrator_email}"
}

# ─── Per-project SAs ─────────────────────────────────────────────────────────

module "project_sa" {
  source   = "../modules/project_sa"
  for_each = var.client_projects

  project_name    = each.key
  project_id      = each.value.project_id
  seed_project_id = var.seed_project_id
  labels          = var.seed_labels

  github_access = each.value.github_access
  wif_pool_name = var.wif_pool_name
  wif_pool_id   = var.wif_pool_id

  depends_on = [
    google_project_iam_member.orchestrator_client_editor,
    google_project_iam_member.orchestrator_client_iam_admin,
  ]
}
