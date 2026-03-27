###############################################################################
# modules/project_sa/variables.tf — Per-project SA module inputs
###############################################################################

variable "project_name" {
  description = "Short name for the client project (used in SA account IDs)"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.project_name))
    error_message = "Project name must be lowercase alphanumeric with hyphens, 2-21 characters."
  }
}

variable "project_id" {
  description = "GCP project ID of the client project"
  type        = string
}

variable "seed_project_id" {
  description = "GCP project ID of the seed project (where WIF pool lives)"
  type        = string
}

variable "labels" {
  description = "Labels to apply to created resources"
  type        = map(string)
  default     = {}
}

variable "runtime_additional_roles" {
  description = "Additional IAM roles to grant to the Runtime SA (beyond defaults)"
  type        = list(string)
  default     = []
}

variable "deploy_additional_roles" {
  description = "Additional IAM roles to grant to the Deploy SA (beyond defaults)"
  type        = list(string)
  default     = []
}

variable "data_additional_roles" {
  description = "Additional IAM roles to grant to the Data SA (beyond defaults)"
  type        = list(string)
  default     = []
}

variable "github_access" {
  description = "List of GitHub identities allowed to deploy via WIF. Each entry creates a separate WIF provider. type='owner' allows all repos from an account/org, type='repo' restricts to a single repo (owner/repo format)."
  type = list(object({
    type  = string
    value = string
  }))
  default = []

  validation {
    condition     = alltrue([for a in var.github_access : contains(["owner", "repo"], a.type)])
    error_message = "Each github_access entry must have type 'owner' or 'repo'."
  }
}

variable "wif_pool_name" {
  description = "Full resource name of the WIF identity pool (from root module)"
  type        = string
  default     = ""
}

variable "wif_pool_id" {
  description = "Short ID of the WIF pool (e.g. cloudseed-github-pool)"
  type        = string
  default     = ""
}
