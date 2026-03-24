###############################################################################
# providers.tf — Provider configuration for per-project SA provisioning
#
# This is a SEPARATE Terraform root module from the main bootstrap.
# It is designed to be run by the Orchestrator SA inside the container,
# managing ONLY per-project Service Accounts (Runtime, Deploy, Data).
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
  }

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
