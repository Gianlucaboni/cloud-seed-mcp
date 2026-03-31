###############################################################################
# Scenario 4: Progetto completo — il tipo di stima che OPA dovra' validare
#
# Simula un tipico progetto cliente: VM + Database + Storage + Cloud Run.
# Questo e' lo scenario piu' realistico per testare l'integrazione con OPA.
# Costo atteso: ~200+ EUR/mese
###############################################################################

# --- VM applicativa ---

resource "google_compute_instance" "app_server" {
  name         = "project-app-server"
  machine_type = "e2-standard-2" # 2 vCPU, 8 GB RAM
  zone         = "europe-west1-b"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 50
      type  = "pd-ssd"
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }
}

# --- Cloud SQL ---

resource "google_sql_database_instance" "project_db" {
  name             = "project-database"
  database_version = "POSTGRES_15"
  region           = "europe-west1"

  settings {
    tier              = "db-n1-standard-1" # 1 vCPU, 3.75 GB RAM
    availability_type = "ZONAL"
    disk_size         = 20
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled = true
    }
  }

  deletion_protection = false
}

# --- Storage bucket ---

resource "google_storage_bucket" "project_data" {
  name          = "project-data-bucket-unique-123"
  location      = "EU"
  storage_class = "STANDARD"
  force_destroy = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90 # giorni
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE" # piu' economico dopo 90 giorni
    }
  }
}

# --- Cloud Run service ---

resource "google_cloud_run_v2_service" "project_api" {
  name     = "project-api"
  location = "europe-west1"

  template {
    containers {
      image = "gcr.io/cloudrun/hello" # immagine placeholder

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    scaling {
      min_instance_count = 0 # scale to zero = paghi solo quando serve
      max_instance_count = 5
    }
  }
}

# --- Artifact Registry (per le immagini Docker) ---

resource "google_artifact_registry_repository" "project_docker" {
  repository_id = "project-docker"
  location      = "europe-west1"
  format        = "DOCKER"
  description   = "Docker images for the project"
}

# --- BigQuery dataset (analytics) ---

resource "google_bigquery_dataset" "project_analytics" {
  dataset_id = "project_analytics"
  location   = "EU"

  default_table_expiration_ms = 7776000000 # 90 giorni
}
