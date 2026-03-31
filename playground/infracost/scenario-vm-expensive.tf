###############################################################################
# Scenario 2: VM costosa — per vedere la differenza con la piccola
#
# Stessa risorsa (google_compute_instance) ma configurazione molto diversa.
# Con le stime piatte di OPA entrambe costerebbero "25 EUR".
# Con Infracost vedrai la differenza reale.
# Costo atteso: ~800+ EUR/mese
###############################################################################

resource "google_compute_instance" "expensive_vm" {
  name         = "test-expensive-vm"
  machine_type = "n2-highmem-16" # 16 vCPU, 128 GB RAM
  zone         = "europe-west1-b"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 500 # GB — disco grande
      type  = "pd-ssd" # SSD invece di standard
    }
  }

  # Disco aggiuntivo (dati)
  attached_disk {
    source      = google_compute_disk.data_disk.id
    device_name = "data"
  }

  network_interface {
    network = "default"
    access_config {}
  }

  # GPU — se vuoi testare il costo con acceleratore, decommenta:
  # guest_accelerator {
  #   type  = "nvidia-tesla-t4"
  #   count = 1
  # }
  # scheduling {
  #   on_host_maintenance = "TERMINATE"
  # }
}

resource "google_compute_disk" "data_disk" {
  name = "test-data-disk"
  type = "pd-ssd"
  size = 200 # GB
  zone = "europe-west1-b"
}
