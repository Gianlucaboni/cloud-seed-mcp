###############################################################################
# Scenario 1: VM piccola — il tipo di risorsa piu' comune
#
# Simula la seed VM di Cloud Seed MCP.
# Costo atteso: ~25 EUR/mese
###############################################################################

resource "google_compute_instance" "small_vm" {
  name         = "test-small-vm"
  machine_type = "e2-medium" # 2 vCPU, 4 GB RAM
  zone         = "europe-west1-b"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30 # GB
      type  = "pd-standard"
    }
  }

  network_interface {
    network = "default"

    # IP pubblico (ha un costo aggiuntivo)
    access_config {}
  }
}
