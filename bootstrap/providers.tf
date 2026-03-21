###############################################################################
# providers.tf — Google provider configuration for Cloud Seed MCP bootstrap
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  # Backend is configured at runtime via install.sh to use a GCS bucket
  # created during the bootstrap process, or local state for the initial run.
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "google" {
  project = var.seed_project_id
  region  = var.default_region
}

provider "google-beta" {
  project = var.seed_project_id
  region  = var.default_region
}
