###############################################################################
# providers.tf — Provider config per gli esperimenti Infracost
#
# Infracost NON esegue terraform init/apply — legge solo i file .tf
# e calcola i costi. Il provider serve solo per definire il progetto
# e la regione di riferimento per i prezzi.
###############################################################################

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "my-fake-project"
  region  = "europe-west1"
}
