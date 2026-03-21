###############################################################################
# variables.tf — Input variables for Cloud Seed MCP bootstrap
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
  description = "GCP organization ID (numeric). Required for IAM deny policies."
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

variable "client_projects" {
  description = "Map of client project configurations. Key is a short name, value contains the project ID."
  type = map(object({
    project_id = string
  }))
  default = {}
}

variable "environment" {
  description = "Environment label (e.g., production, staging)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "Environment must be one of: production, staging, development."
  }
}

variable "seed_labels" {
  description = "Common labels applied to all resources created by the bootstrap"
  type        = map(string)
  default = {
    managed-by = "cloud-seed-mcp"
    component  = "bootstrap"
  }
}
