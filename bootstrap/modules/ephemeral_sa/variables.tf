###############################################################################
# modules/ephemeral_sa/variables.tf — Ephemeral SA module inputs
###############################################################################

variable "seed_project_id" {
  description = "GCP project ID of the seed project (where ephemeral SAs live)"
  type        = string
}

variable "default_region" {
  description = "Default GCP region for Cloud Scheduler jobs"
  type        = string
}

variable "labels" {
  description = "Labels to apply to created resources"
  type        = map(string)
  default     = {}
}

variable "ttl_hours" {
  description = "Default time-to-live in hours for ephemeral SAs before automatic cleanup"
  type        = number
  default     = 4

  validation {
    condition     = var.ttl_hours >= 1 && var.ttl_hours <= 24
    error_message = "TTL must be between 1 and 24 hours."
  }
}

variable "cleanup_schedule" {
  description = "Cron schedule for the ephemeral SA cleanup job (Cloud Scheduler)"
  type        = string
  default     = "0 */1 * * *" # Every hour
}

variable "max_concurrent_ephemeral_sas" {
  description = "Maximum number of ephemeral SAs that can exist simultaneously"
  type        = number
  default     = 10
}
