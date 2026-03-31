# Infracost — Studio e sperimentazione

Questa cartella e' un playground per studiare Infracost.
E' in `.gitignore` — nulla qui finisce nel repo.

## Setup

```bash
# 1. Installa Infracost
curl -fsSL https://raw.githubusercontent.com/infracost/infracost/master/scripts/install.sh | sh

# 2. Registra una API key gratuita (serve per il database prezzi)
infracost auth login

# 3. Verifica
infracost --version
```

## Esperimenti

```bash
cd playground/infracost

# Stima costi di un singolo file
infracost breakdown --path scenario-vm.tf

# Stima con output JSON (quello che useremmo con OPA)
infracost breakdown --path scenario-vm.tf --format json > output-vm.json

# Stima di tutti i .tf nella cartella
infracost breakdown --path .

# Confronto tra due scenari (diff)
infracost diff --path scenario-vm-expensive.tf --compare-to scenario-vm.tf
```

## File mock

| File | Cosa simula | Costo atteso |
|------|-------------|-------------|
| `scenario-vm.tf` | VM piccola (e2-medium) | ~25 EUR/mese |
| `scenario-vm-expensive.tf` | VM grande (n2-highmem-16) | ~800+ EUR/mese |
| `scenario-database.tf` | Cloud SQL PostgreSQL | ~50-100 EUR/mese |
| `scenario-full-project.tf` | Progetto completo (VM + DB + Storage + Cloud Run) | ~200+ EUR/mese |
| `providers.tf` | Configurazione provider Google (comune a tutti) |
