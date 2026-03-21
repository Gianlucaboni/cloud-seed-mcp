###############################################################################
# modules/ephemeral_sa/outputs.tf — Ephemeral SA module outputs
###############################################################################

output "pool_manager_sa_email" {
  description = "Email of the ephemeral SA pool manager"
  value       = google_service_account.pool_manager.email
}

output "pool_manager_sa_name" {
  description = "Fully qualified name of the pool manager SA"
  value       = google_service_account.pool_manager.name
}

output "cleanup_function_sa_email" {
  description = "Email of the cleanup function SA"
  value       = google_service_account.cleanup_function.email
}

output "cleanup_topic_name" {
  description = "Name of the Pub/Sub topic for cleanup triggers"
  value       = google_pubsub_topic.ephemeral_cleanup.name
}

output "cleanup_job_name" {
  description = "Name of the Cloud Scheduler cleanup job"
  value       = google_cloud_scheduler_job.ephemeral_cleanup.name
}

output "ephemeral_readonly_role_id" {
  description = "ID of the custom read-only role for ephemeral SAs"
  value       = google_project_iam_custom_role.ephemeral_readonly.id
}
