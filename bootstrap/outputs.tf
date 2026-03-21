###############################################################################
# outputs.tf — Bootstrap outputs
###############################################################################

# ─── Installer SA ────────────────────────────────────────────────────────────
output "installer_sa_email" {
  description = "Email of the Installer SA (disabled after bootstrap)"
  value       = google_service_account.installer.email
}

# ─── Orchestrator SA ─────────────────────────────────────────────────────────
output "orchestrator_sa_email" {
  description = "Email of the Orchestrator SA"
  value       = google_service_account.orchestrator.email
}

# ─── Per-Project SAs ─────────────────────────────────────────────────────────
output "project_sa_emails" {
  description = "Map of client project names to their SA emails (runtime, deploy, data)"
  value = {
    for name, mod in module.project_sa : name => {
      runtime = mod.runtime_sa_email
      deploy  = mod.deploy_sa_email
      data    = mod.data_sa_email
    }
  }
}

# ─── Ephemeral SA ────────────────────────────────────────────────────────────
output "ephemeral_sa_pool_email" {
  description = "Email of the Ephemeral SA pool manager"
  value       = module.ephemeral_sa.pool_manager_sa_email
}

output "ephemeral_cleanup_job_name" {
  description = "Name of the Cloud Scheduler job that cleans up expired ephemeral SAs"
  value       = module.ephemeral_sa.cleanup_job_name
}
