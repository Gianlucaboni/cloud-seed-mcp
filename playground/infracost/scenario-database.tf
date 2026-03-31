###############################################################################
# Scenario 3: Cloud SQL PostgreSQL
#
# Simula un database che un cliente potrebbe richiedere.
# Infracost calcola: istanza + storage + backup + HA (se abilitato)
# Costo atteso: ~50-100 EUR/mese (single), ~100-200 EUR/mese (HA)
###############################################################################

# --- Database piccolo (sviluppo) ---

resource "google_sql_database_instance" "small_db" {
  name             = "test-small-db"
  database_version = "POSTGRES_15"
  region           = "europe-west1"

  settings {
    tier              = "db-f1-micro" # Shared CPU, 0.6 GB RAM — il piu' economico
    availability_type = "ZONAL"       # Niente HA = meno costo
    disk_size         = 10            # GB
    disk_type         = "PD_SSD"

    backup_configuration {
      enabled = true
    }
  }

  deletion_protection = false
}

# --- Database produzione (HA) ---

resource "google_sql_database_instance" "prod_db" {
  name             = "test-prod-db"
  database_version = "POSTGRES_15"
  region           = "europe-west1"

  settings {
    tier              = "db-n1-standard-2" # 2 vCPU, 7.5 GB RAM
    availability_type = "REGIONAL"          # HA = replica in altra zona
    disk_size         = 50                  # GB
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }

  deletion_protection = false
}
