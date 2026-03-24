###############################################################################
# variables.tf — Input variables for per-project SA provisioning
#
# These are the ONLY variables the Orchestrator needs to create per-project
# Service Accounts. No ephemeral SA, deny policy, or installer variables.
###############################################################################

variable "seed_project_id" {
  description = "GCP project ID where the Cloud Seed MCP system lives"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.seed_project_id))
    error_message = "Project ID must be 6-30 characters, lowercase letters, digits, and hyphens."
  }
}

variable "org_id" {
  description = "GCP organization ID (numeric)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.org_id))
    error_message = "Organization ID must be a numeric string."
  }
}

variable "default_region" {
  description = "Default GCP region for resources"
  type        = string
  default     = "europe-west1"
}

variable "wif_pool_name" {
  description = "Full resource name of the GitHub WIF pool (from bootstrap infra output)"
  type        = string
  default     = ""
}

variable "wif_pool_id" {
  description = "Short ID of the WIF pool (e.g. cloudseed-github-pool)"
  type        = string
  default     = "cloudseed-github-pool"
}

variable "client_projects" {
  description = "Map of client project configurations. Key is a short name, value contains the project ID and optional github_repo."
  type = map(object({
    project_id  = string
    github_repo = optional(string, "")
  }))
  default = {}
}

variable "seed_labels" {
  description = "Common labels applied to all resources"
  type        = map(string)
  default = {
    managed-by = "cloud-seed-mcp"
    component  = "project-sa"
  }
}
