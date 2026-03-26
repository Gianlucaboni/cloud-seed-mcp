###############################################################################
# main.tf — Per-project SA provisioning (run by Orchestrator)
#
# This root module manages ONLY the per-project Service Accounts:
#   - SA Runtime (Cloud Run / VM operation)
#   - SA Deploy  (image push + deployment via WIF)
#   - SA Data    (read/write on buckets and databases)
#
# It is separate from the main bootstrap, which manages one-time infra
# (SA Installer, SA Orchestrator, deny policies, WIF pool, ephemeral SA).
# The Orchestrator has the permissions needed to manage these resources:
#   - iam.serviceAccountAdmin on seed project (create/manage SAs)
#   - resourcemanager.projectIamAdmin on seed project (bind roles)
#   - editor + projectIamAdmin on client projects (grant SA permissions)
###############################################################################

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
}
