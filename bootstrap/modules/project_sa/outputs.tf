###############################################################################
# modules/project_sa/outputs.tf — Per-project SA module outputs
###############################################################################

output "runtime_sa_email" {
  description = "Email of the Runtime SA for this project"
  value       = google_service_account.runtime.email
}

output "runtime_sa_name" {
  description = "Fully qualified name of the Runtime SA"
  value       = google_service_account.runtime.name
}

output "deploy_sa_email" {
  description = "Email of the Deploy SA for this project"
  value       = google_service_account.deploy.email
}

output "deploy_sa_name" {
  description = "Fully qualified name of the Deploy SA"
  value       = google_service_account.deploy.name
}

output "data_sa_email" {
  description = "Email of the Data SA for this project"
  value       = google_service_account.data.email
}

output "data_sa_name" {
  description = "Fully qualified name of the Data SA"
  value       = google_service_account.data.name
}

output "wif_provider_names" {
  description = "Map of GitHub access keys to their WIF provider resource names"
  value = {
    for key, provider in google_iam_workload_identity_pool_provider.github :
    key => provider.name
  }
}
