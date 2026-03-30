# Bootstrap — Deep Dive

Riassunto della sessione di studio della directory `bootstrap/`.
Copre la struttura dei file, la sintassi Terraform, il flusso dei dati,
e come il sistema evolve dopo il primo bootstrap.

---

## Struttura della directory

```
bootstrap/
├── install.sh              # Script lanciato dall'umano per l'installazione iniziale
├── vm-startup.sh           # Script che parte automaticamente sulla VM creata
├── main.tf                 # File principale — collega moduli e abilita API
├── providers.tf            # Dice a Terraform "usa Google Cloud"
├── variables.tf            # Dichiarazione dei parametri in input
├── outputs.tf              # Valori restituiti dopo l'esecuzione
├── sa_hierarchy.tf         # Crea SA Installer + SA Orchestrator
├── deny_policy.tf          # Regole di sicurezza invalicabili
├── modules/
│   ├── project_sa/         # Modulo: crea 3 SA per ogni progetto cliente
│   └── ephemeral_sa/       # Modulo: fabbrica di SA temporanei
├── projects/               # Terraform SEPARATO, usato dall'Orchestrator dopo il bootstrap
└── tests/
    └── validate.sh         # Verifica permessi
```

**Regola fondamentale:** Terraform prende tutti i `.tf` nella stessa cartella e li
tratta come un unico blocco. La separazione in file e' solo organizzativa.
Le sottocartelle (`modules/`, `projects/`, `tests/`) NON vengono lette
automaticamente — servono chiamate esplicite (`module {}`) o un `terraform apply`
separato.

---

## Sintassi Terraform — le basi

### Dichiarazione di una risorsa

```hcl
resource "google_service_account" "installer" {
  account_id   = "cloudseed-installer"
  display_name = "Cloud Seed MCP — Installer (bootstrap only)"
  project      = var.seed_project_id
}
```

- `resource` — parola chiave: "voglio creare qualcosa"
- `"google_service_account"` — il **tipo** (definito dal provider Google). Come uno stampo
- `"installer"` — il **nome locale** (lo inventi tu, serve solo dentro i file .tf)
- Le righe dentro `{}` — parametri della risorsa

Due risorse possono avere lo stesso tipo ma devono avere nomi locali diversi.

### Assegnazione di un ruolo

```hcl
resource "google_project_iam_member" "installer_sa_admin" {
  project = var.seed_project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.installer.email}"
}
```

Si legge: "nel progetto X, dai il ruolo Y all'utente Z".

La sintassi `${google_service_account.installer.email}` e' un **riferimento**:
- `google_service_account` — tipo della risorsa
- `.installer` — nome locale dato sopra
- `.email` — attributo restituito da GCP dopo la creazione

Terraform deduce automaticamente l'ordine: prima crea il SA, poi assegna i ruoli.

### Variabili (`variable`) e locals (`locals`)

```hcl
# variable — parametro in input (viene dall'esterno)
variable "seed_project_id" {
  type = string
}

# locals — valore calcolato (costruito internamente)
locals {
  orchestrator_email = "cloudseed-orchestrator@${var.seed_project_id}.iam.gserviceaccount.com"
}
```

- `var.seed_project_id` — valore passato dall'esterno (da .tfvars, CLI, o env var)
- `local.orchestrator_email` — valore costruito una volta e riusato nel file

### Moduli (`module`)

```hcl
module "project_sa" {
  source   = "./modules/project_sa"
  for_each = var.client_projects

  project_name = each.key
  project_id   = each.value.project_id
}
```

Un modulo e' come una funzione: `source` dice dove sta il codice, i parametri
vengono passati esplicitamente. `for_each` lo ripete per ogni elemento della mappa.

### Ruoli predefiniti vs custom

```hcl
# Ruolo predefinito (menu fisso di Google — prendi tutto o niente)
role = "roles/iam.serviceAccountAdmin"

# Ruolo custom (menu alla carta — scegli permesso per permesso)
resource "google_project_iam_custom_role" "orchestrator_ops" {
  role_id     = "cloudSeedOrchestratorOps"
  permissions = [
    "run.services.create",
    "run.services.update",
    "run.services.get",
    # (niente run.services.delete — non vogliamo che possa cancellare)
  ]
}
```

I ruoli predefiniti si usano quando il pacchetto corrisponde a cio' che serve.
Il ruolo custom quando servono permessi specifici da aree diverse senza dare troppo.

---

## Flusso dei dati: da install.sh a Terraform

```
Tu (umano)
  ./install.sh --seed-project-id=my-project --org-id=123456
      |
      |  Lo script salva il valore in variabile bash SEED_PROJECT_ID
      |  e poi genera un file:
      |
      |  cat > bootstrap.auto.tfvars <<EOF
      |  seed_project_id    = "my-project"
      |  org_id             = "123456"
      |  billing_account_id = "ABCDE-12345"
      |  EOF
      |
      v
  Terraform carica automaticamente *.auto.tfvars
      |
      v
  variables.tf valida e rende disponibili le variabili
      |
      v
  Tutti i .tf della cartella le usano come var.seed_project_id
```

Il file `bootstrap.auto.tfvars` e' il ponte tra bash e Terraform.
Non tutte le variabili vengono passate: quelle con `default` in `variables.tf`
(come `default_region`, `client_projects`, `environment`) usano il valore predefinito.

---

## I 4 livelli di Service Account

### Livello 1: SA Installer (sa_hierarchy.tf)
- Crea tutto durante il bootstrap
- 4 ruoli: serviceAccountAdmin, securityAdmin, projectIamAdmin, serviceUsageAdmin
- **Disabilitato permanentemente** alla fine di install.sh

### Livello 2: SA Orchestrator (sa_hierarchy.tf)
- Gestore permanente del sistema
- Permessi sul seed project (gestire SA, IAM, WIF, Scheduler)
- Permessi a livello organizzazione (creare progetti, billing, abilitare API)
- Permessi sui progetti cliente (editor, IAM admin, SA admin, service usage)
- Ruolo custom `cloudSeedOrchestratorOps` per operazioni quotidiane
- Soggetto a deny policy che gli impediscono azioni distruttive

### Livello 3: SA per-Progetto (modules/project_sa/)
Creati **nel progetto del cliente** (non nel seed) per isolamento strutturale.

| SA | Account ID | Cosa puo' fare |
|----|-----------|----------------|
| Runtime | `cs-{nome}-runtime` | Far girare app, scrivere log/metriche/tracce |
| Deploy  | `cs-{nome}-deploy`  | Push immagini, deploy Cloud Run, act-as Runtime |
| Data    | `cs-{nome}-data`    | BigQuery, Storage, Cloud SQL, Firestore (r/w) |

### Livello 4: SA Effimeri (modules/ephemeral_sa/)
- SA temporanei creati dal Tool Forge per testare nuovi tool
- Sola lettura, TTL 4 ore, pulizia automatica via Cloud Scheduler

---

## Il bootstrap NON tocca `bootstrap/projects/`

Al primo bootstrap:
- `client_projects = {}` (mappa vuota)
- Il `for_each` in `main.tf` non produce nulla
- I moduli `project_sa` ed `ephemeral_sa` vengono chiamati, ma `project_sa` non crea SA perche' la mappa e' vuota
- La cartella `projects/` non viene toccata — `install.sh` funzionerebbe anche senza di essa

---

## Dopo il bootstrap: la mappa che cresce

Quando il sistema e' operativo e il cliente chiede un nuovo progetto,
l'Orchestrator lavora in `bootstrap/projects/`. Il file `.tfvars` viene aggiornato
e la mappa `client_projects` cresce:

```hcl
# Dopo il primo progetto
client_projects = {
  "iot-sensors" = {
    project_id    = "acme-iot-sensors-prod"
    github_access = [
      { type = "owner", value = "AcmeCorp" }
    ]
  }
}

# Dopo il secondo progetto — la mappa cresce
client_projects = {
  "iot-sensors" = {
    project_id    = "acme-iot-sensors-prod"
    github_access = [
      { type = "owner", value = "AcmeCorp" }
    ]
  }
  "analytics" = {
    project_id    = "acme-analytics-prod"
    github_access = [
      { type = "repo", value = "AcmeCorp/analytics-dashboard" }
    ]
  }
}
```

Terraform ha uno **state** che ricorda cosa ha gia' creato. Rieseguendo
`terraform apply`, crea solo le risorse per i progetti nuovi senza toccare
quelli esistenti.

In `bootstrap/projects/main.tf` succede in sequenza:
1. L'Orchestrator si auto-assegna i permessi sul nuovo progetto (5 ruoli)
2. `depends_on` garantisce che quei permessi esistano prima di proseguire
3. Il modulo `project_sa` crea i 3 SA (Runtime, Deploy, Data) nel progetto cliente

Il `local.orchestrator_email` ricostruisce l'email dell'Orchestrator "a mano" perche'
in questo Terraform separato il SA non viene creato (esiste gia' dal bootstrap):

```hcl
locals {
  orchestrator_email = "cloudseed-orchestrator@${var.seed_project_id}.iam.gserviceaccount.com"
}
```

---

## Comandi di verifica post-bootstrap

Una volta che il seed e il container sono attivi, questi comandi permettono
di verificare che il sistema evolve correttamente man mano che nuovi progetti
vengono creati.

### Verificare lo state di Terraform dentro il container

```bash
# Entra nel container core-mcp
docker exec -it core-mcp bash

# Vai nella cartella projects (quella usata dall'Orchestrator)
cd /app/bootstrap/projects

# Vedi lo state corrente — quali risorse Terraform conosce
terraform state list

# Dopo aver creato un progetto, ripeti e vedrai nuove risorse:
#   google_project_iam_member.orchestrator_client_editor["iot-sensors"]
#   module.project_sa["iot-sensors"].google_service_account.runtime
#   module.project_sa["iot-sensors"].google_service_account.deploy
#   module.project_sa["iot-sensors"].google_service_account.data
```

### Verificare il file .tfvars (la mappa che cresce)

```bash
# Dentro il container, guarda il file tfvars generato dall'Orchestrator
cat /app/bootstrap/projects/*.tfvars

# Dopo il primo progetto vedrai la mappa con un elemento
# Dopo il secondo, due elementi, ecc.
```

### Verificare i SA creati su GCP

```bash
# Lista tutti i SA nel progetto cliente
gcloud iam service-accounts list --project=acme-iot-sensors-prod

# Dovresti vedere:
#   cs-iot-sensors-runtime@acme-iot-sensors-prod.iam.gserviceaccount.com
#   cs-iot-sensors-deploy@acme-iot-sensors-prod.iam.gserviceaccount.com
#   cs-iot-sensors-data@acme-iot-sensors-prod.iam.gserviceaccount.com

# Verifica i ruoli di un SA specifico
gcloud projects get-iam-policy acme-iot-sensors-prod \
  --flatten="bindings[].members" \
  --filter="bindings.members:cs-iot-sensors-runtime" \
  --format="table(bindings.role)"
```

### Verificare il WIF (collegamento GitHub)

```bash
# Lista i provider WIF creati per il progetto
gcloud iam workload-identity-pools providers list \
  --workload-identity-pool=cloudseed-github-pool \
  --location=global \
  --project=<SEED_PROJECT_ID>
```

### Confronto prima/dopo

```bash
# PRIMA di creare un nuovo progetto — salva lo stato
terraform state list > /tmp/state-before.txt

# Crea il progetto tramite il sistema MCP...

# DOPO — confronta
terraform state list > /tmp/state-after.txt
diff /tmp/state-before.txt /tmp/state-after.txt

# Vedrai le nuove risorse aggiunte per il nuovo progetto
```
