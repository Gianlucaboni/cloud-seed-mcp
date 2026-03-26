# Terraform - Come funziona

## Cos'è Terraform

Terraform è uno strumento di Infrastructure as Code (IaC). Scrivi dei file che descrivono **COSA vuoi** (un server, un database, un service account) e Terraform si occupa di **COME crearlo** su Google Cloud (o AWS, Azure, etc.).

La differenza con `gcloud`:
- **gcloud** è imperativo: "crea questo server" → se esiste già, errore
- **Terraform** è dichiarativo: "voglio che esista questo server" → se esiste già, niente da fare

---

## I file .tf

Tutti i file `.tf` in una cartella formano un **modulo**. Terraform li legge tutti insieme — non importa come li chiami, ma per convenzione:

| File | Cosa contiene |
|------|--------------|
| `variables.tf` | Dichiarazione degli input (tipo, default, validazione) |
| `main.tf` | Le risorse da creare |
| `outputs.tf` | I valori che il modulo espone |
| `providers.tf` | Quale cloud provider usare e versione |

### Esempio: variables.tf

```hcl
variable "project_id" {
  description = "ID del progetto GCP"
  type        = string
}

variable "region" {
  description = "Regione GCP"
  type        = string
  default     = "europe-west1"    # se non la passi, usa questo
}
```

### Esempio: main.tf (crea un service account)

```hcl
resource "google_service_account" "deploy" {
  account_id   = "my-deploy-sa"
  display_name = "Deploy SA"
  project      = var.project_id      # usa la variabile
}
```

### Esempio: outputs.tf

```hcl
output "deploy_sa_email" {
  value = google_service_account.deploy.email
}
```

---

## Come si passano i valori alle variabili

Ci sono 3 modi principali:

### 1. File .tfvars (il più comune)

Terraform legge **automaticamente** i file `*.auto.tfvars` e `*.auto.tfvars.json`:

```hcl
# bootstrap.auto.tfvars
seed_project_id = "cloud-seed-20260325"
org_id          = "95628101394"
```

Oppure in JSON:

```json
// projects.auto.tfvars.json
{
  "seed_project_id": "cloud-seed-20260325",
  "org_id": "95628101394"
}
```

### 2. Da linea di comando

```bash
terraform apply -var="project_id=my-project"
```

### 3. Variabili d'ambiente

```bash
export TF_VAR_project_id="my-project"
terraform apply
```

---

## Root Module vs Child Module

Un **ROOT MODULE** è la cartella dove fai `terraform init` e `terraform apply`. Ha il suo `terraform.tfstate` (il file che traccia cosa è stato creato).

Un **CHILD MODULE** è codice riusabile che viene chiamato da un root module con `module { source = "..." }`. **Non ha state proprio** — le sue risorse finiscono nello state del root.

### In Cloud Seed MCP abbiamo 2 root module separati:

```
bootstrap/                      ← ROOT MODULE 1 (eseguito da te, una volta)
├── main.tf                       Crea: WIF pool, API enable
├── sa_hierarchy.tf               Crea: SA Installer, SA Orchestrator
├── deny_policy.tf                Crea: deny policies
├── terraform.tfstate             ⭐ Traccia tutto quanto sopra
└── modules/
    ├── project_sa/             ← CHILD MODULE (riusabile)
    │   ├── main.tf               Crea: 3 SA per progetto + WIF provider
    │   └── variables.tf
    └── ephemeral_sa/           ← CHILD MODULE
        └── main.tf               Crea: SA pool manager + cleanup

bootstrap/projects/             ← ROOT MODULE 2 (eseguito dall'Orchestrator)
├── main.tf                       Chiama project_sa per ogni progetto
├── terraform.tfstate             ⭐ Traccia SOLO le SA dei progetti client
└── projects.auto.tfvars.json     Input: lista dei progetti client
```

**Perché 2 root module separati?**
- `bootstrap/` → eseguito **una volta sola** da te (admin) con SA Installer
- `bootstrap/projects/` → eseguito **dall'Orchestrator** ogni volta che crei un progetto
- Hanno state separati = non si pestano i piedi

---

## Il terraform.tfstate

È un file JSON che contiene lo stato di **TUTTE** le risorse create da Terraform. È la "fonte di verità" di Terraform.

Esempio semplificato:

```json
{
  "outputs": {
    "wif_pool_name": {
      "value": "projects/776728062120/.../cloudseed-github-pool"
    }
  },
  "resources": [
    {
      "type": "google_service_account",
      "name": "orchestrator",
      "instances": [{
        "attributes": {
          "email": "cloudseed-orchestrator@cloud-seed-20260325.iam..."
        }
      }]
    }
  ]
}
```

### Regola fondamentale

| Situazione | Cosa succede |
|-----------|-------------|
| Cancelli il tfstate | Terraform "dimentica" le risorse — ma **continuano a esistere su GCP!** |
| Risorsa nel tfstate ma non su GCP | `terraform plan` → "will be created" |
| Risorsa su GCP ma non nel tfstate | Terraform non la vede → prova a crearla → errore 409 "already exists" |

Per questo quando facciamo `--clean` nel bootstrap dobbiamo cancellare **ANCHE le risorse GCP**, non solo lo state.

---

## Il flusso plan → apply

```
1. terraform plan
   ├── Legge i file .tf        (cosa VUOI)
   ├── Legge il tfstate         (cosa HAI)
   ├── Chiede a GCP lo stato    (refresh)
   └── Calcola il diff
       Output: "Plan: 3 to add, 1 to change, 0 to destroy"

2. terraform apply
   ├── Esegue il piano
   ├── Aggiorna il tfstate
   └── Output: "Apply complete! Resources: 3 added, 1 changed"
```

---

## for_each — Creare risorse in loop

Terraform può creare N risorse dallo stesso blocco:

```hcl
variable "client_projects" {
  type = map(object({
    project_id  = string
    github_repo = optional(string, "")
  }))
}

module "project_sa" {
  source   = "../modules/project_sa"
  for_each = var.client_projects       # per ogni progetto

  project_name = each.key              # la chiave (es. "landing-page-seed")
  project_id   = each.value.project_id # il valore
}
```

Se `client_projects` ha 3 entries → Terraform crea 3 istanze del modulo, ognuna con il suo set di SA.

---

## Come Cloud Seed MCP usa Terraform

Il flusso quando chiedi "crea un progetto per la landing page":

```
1. project_create (Python, nel container core-mcp)
   │
   │  gcloud projects create landing-page-seed
   │  gcloud billing projects link ...
   │  gcloud services enable ...
   │
   │  Scrive projects.auto.tfvars.json:
   │  {
   │    "client_projects": {
   │      "landing-page-seed": { "project_id": "landing-page-seed" }
   │    },
   │    "github_owner": "Gianlucaboni",
   │    "wif_pool_name": "projects/.../cloudseed-github-pool"
   │  }
   │
   │  terraform init
   │  terraform apply -auto-approve
   ▼
2. bootstrap/projects/main.tf
   │
   │  module "project_sa" {
   │    for_each = var.client_projects
   │    github_owner = var.github_owner
   │  }
   ▼
3. modules/project_sa/main.tf
   │
   │  Crea: google_service_account.runtime
   │  Crea: google_service_account.deploy
   │  Crea: google_service_account.data
   │  Crea: google_iam_workload_identity_pool_provider.github
   │        (attribute_condition = "attribute.repository_owner == 'Gianlucaboni'")
   │  Crea: google_service_account_iam_member.deploy_wif_binding
   ▼
4. Risultato: GitHub Actions di qualsiasi repo di Gianlucaboni
   può autenticarsi come SA Deploy e fare deploy su Cloud Run
```

---

## I comandi principali

| Comando | Cosa fa |
|---------|---------|
| `terraform init` | Scarica i provider, inizializza la cartella |
| `terraform plan` | Mostra cosa farebbe (senza fare nulla) |
| `terraform apply` | Esegue il piano: crea/modifica/cancella |
| `terraform destroy` | Cancella TUTTO quello che è nello state |
| `terraform output` | Mostra i valori degli output |
| `terraform state list` | Mostra tutte le risorse tracciate |
| `terraform import` | Importa una risorsa GCP esistente nello state |

---

## Glossario

| Termine | Significato |
|---------|-------------|
| **resource** | Una risorsa GCP (SA, VM, bucket, etc.) |
| **provider** | Il plugin che parla con GCP (`hashicorp/google`) |
| **state/tfstate** | Il file che traccia cosa Terraform ha creato |
| **plan** | Il diff tra stato desiderato e stato attuale |
| **apply** | Esegui il piano |
| **module** | Una cartella con file .tf riusabili |
| **variable** | Input di un modulo |
| **output** | Valore esposto da un modulo |
| **for_each** | Crea N risorse da una mappa |
| **.auto.tfvars** | File letto automaticamente per popolare le variabili |
