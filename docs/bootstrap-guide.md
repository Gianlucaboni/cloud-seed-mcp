# Cloud Seed MCP — Bootstrap Guide

How to create a new seed from scratch.

## Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     YOUR MAC (one-time)                       │
│                                                               │
│  1. Create GCP project under the org                         │
│  2. Link billing                                              │
│  3. Run install.sh                                            │
│     │                                                         │
│     ├── Enables 15 APIs on seed project                      │
│     ├── terraform apply:                                      │
│     │   ├── Creates SA Installer (then disables it)          │
│     │   ├── Creates SA Orchestrator + org-level permissions  │
│     │   ├── Creates 4 deny policies                          │
│     │   ├── Creates WIF pool for GitHub Actions              │
│     │   └── Creates ephemeral SA pool + cleanup job          │
│     │                                                         │
│     └── Creates VM with SA Orchestrator attached             │
│         │                                                     │
│         └── vm-startup.sh (runs automatically at boot)       │
│             ├── Installs Docker                               │
│             ├── Clones repo from GitHub                       │
│             ├── Creates .env                                  │
│             └── docker compose up                             │
│                 ├── state-store (PostgreSQL) ✓                │
│                 ├── opa (Policy Engine) ✓                     │
│                 ├── tool-forge ✓                               │
│                 └── core-mcp (port 8000) ✓                    │
│                                                               │
│  4. Grant billing.user to SA Orchestrator                    │
│  5. Set env vars on VM                                        │
│  6. Start SSH tunnel                                          │
│  7. Configure Claude Desktop                                  │
│                                                               │
│  ✅ Seed operational                                          │
└──────────────────────────────────────────────────────────────┘
```

## Prerequisites

- GCP account with an **organization** (e.g. `mycompany.com`)
- Active **billing account**
- **gcloud CLI** installed and authenticated (`gcloud auth login`)
- **Terraform** installed (`brew install terraform` on macOS)
- **cloud-seed-mcp** repo cloned locally
- **Claude Desktop** installed
- **Node.js/npx** installed (for `mcp-remote`)

## Step-by-step

### Step 1 — Create the seed project

```bash
gcloud projects create MY-SEED-PROJECT \
  --name="Cloud Seed MCP" \
  --organization=ORG_ID
```

Replace `MY-SEED-PROJECT` with your chosen project ID (6-30 chars, lowercase, hyphens allowed) and `ORG_ID` with your numeric organization ID.

To find your org ID:
```bash
gcloud organizations list
```

### Step 2 — Link billing

```bash
# Find your billing account
gcloud billing accounts list

# Link it to the project
gcloud billing projects link MY-SEED-PROJECT \
  --billing-account=BILLING_ACCOUNT_ID
```

> **Note:** If the billing account belongs to a different GCP account than the org, you need to run this command from that account, or link it from the [GCP Console](https://console.cloud.google.com/billing/linkedaccount).

### Step 3 — Authenticate for Terraform

Terraform uses **Application Default Credentials** (ADC), not your gcloud login. You must authenticate separately:

```bash
gcloud auth application-default login
```

This opens the browser. Authenticate with your **org admin account** (the one with `roles/resourcemanager.organizationAdmin`).

### Step 4 — Run the bootstrap

```bash
cd cloud-seed-mcp/bootstrap

./install.sh \
  --seed-project-id=MY-SEED-PROJECT \
  --org-id=ORG_ID \
  --billing-account=BILLING_ACCOUNT_ID \
  --auto-approve
```

This takes ~5 minutes and performs 6 steps:

1. **Validates prerequisites** — checks gcloud, terraform, authentication, project access
2. **Enables APIs** — 15 GCP APIs including Compute, IAM, BigQuery, Cloud Run, etc.
3. **Terraform init** — downloads providers (google, google-beta, random)
4. **Terraform apply** — creates the full SA hierarchy, deny policies, WIF pool
5. **Disables SA Installer** — the installer SA is permanently disabled after use
6. **Creates the VM** — `cloud-seed-vm` with SA Orchestrator attached, runs startup script

Optional flags:
- `--vm-zone=ZONE` — VM zone (default: `europe-west1-b`)
- `--vm-machine-type=TYPE` — VM type (default: `e2-medium`)
- `--skip-disable` — don't disable installer SA (dev only)
- `--skip-vm` — don't create the VM (SA hierarchy only)

### Step 5 — Grant billing access to SA Orchestrator

This step is needed when the billing account belongs to a different GCP account than the org admin running the bootstrap (common with personal billing + org setup).

```bash
# Run this from the account that OWNS the billing account
gcloud billing accounts add-iam-policy-binding BILLING_ACCOUNT_ID \
  --member="serviceAccount:cloudseed-orchestrator@MY-SEED-PROJECT.iam.gserviceaccount.com" \
  --role="roles/billing.user"
```

> This cannot be done in Terraform when the billing account belongs to a different identity domain.

### Step 6 — Wait for VM startup (~5 min)

```bash
# Watch the startup log
gcloud compute ssh cloud-seed-vm \
  --zone=europe-west1-b \
  --project=MY-SEED-PROJECT \
  -- "tail -f /var/log/cloud-seed-startup.log"
```

Wait until you see:
```
=== Cloud Seed MCP startup complete ===
```
and all 4 containers showing `(healthy)`.

### Step 7 — Set environment variables on VM

The Core MCP needs to know the seed project ID and org ID for project creation:

```bash
gcloud compute ssh cloud-seed-vm \
  --zone=europe-west1-b \
  --project=MY-SEED-PROJECT \
  -- "sudo bash -c '
    echo CORE_MCP_SEED_PROJECT_ID=MY-SEED-PROJECT >> /opt/cloud-seed-mcp/.env
    echo CORE_MCP_ORG_ID=ORG_ID >> /opt/cloud-seed-mcp/.env
    cd /opt/cloud-seed-mcp && docker compose up -d --force-recreate core-mcp
  '"
```

### Step 8 — Start SSH tunnel

```bash
gcloud compute ssh cloud-seed-vm \
  --zone=europe-west1-b \
  --project=MY-SEED-PROJECT \
  -- -L 8000:localhost:8000 -N
```

> This command stays open — don't close it. It forwards your local port 8000 to the VM's port 8000.

If port 8000 is already in use:
```bash
kill $(lsof -ti:8000)
```

### Step 9 — Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cloud-seed": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/mcp"]
    }
  }
}
```

> **Important:** Use `/mcp` without trailing slash. `/mcp/` causes a 307 redirect that breaks the connection.

Restart Claude Desktop: `Cmd+Q` then reopen.

### Step 10 — Verify

In Claude Desktop, ask: *"list my projects"*

You should see your seed project listed. Then try: *"create a new project called my-first-project"*

## What gets created

```
Organization (your-org.com)
│
└── MY-SEED-PROJECT
    │
    │ Service Accounts:
    ├── cloudseed-installer            DISABLED after bootstrap
    ├── cloudseed-orchestrator         attached to VM, operates everywhere
    ├── cloudseed-ephemeral-mgr        manages sandbox SAs for Tool Forge
    └── cloudseed-sa-cleanup           periodic cleanup of expired SAs
    │
    │ Deny Policies (hard blocks on Orchestrator):
    ├── deny-project-deletion          cannot delete any GCP project
    ├── deny-modify-critical-sas       cannot disable/delete SAs in seed
    ├── deny-seed-iam-modification     cannot change IAM roles/SAs in seed
    └── deny-cross-project-secrets     cannot read secrets in any project
    │
    │ Infrastructure:
    ├── WIF Pool (cloudseed-github-pool)
    ├── Cloud Scheduler (ephemeral SA cleanup, hourly)
    └── Pub/Sub topic (cleanup trigger)
    │
    │ VM: cloud-seed-vm
    └── Docker Compose (seed-net network)
        ├── core-mcp       :8000   MCP server, 17 tools
        ├── opa             :8181   Policy engine, 4 Rego policies
        ├── tool-forge      :8001   Tool generator + registry
        └── state-store     :5432   PostgreSQL (seeddb)
```

## When you create a client project

When you ask Claude to create a project (e.g. *"create project my-pets"*), the system does:

```
Claude Desktop → MCP → project_create tool
│
├── gcloud projects create my-pets --organization=ORG_ID
├── Link billing account
├── Enable 9 default APIs
├── Create Terraform directory at /opt/cloud-seed-mcp/projects/my-pets/
│
└── Update bootstrap tfvars + terraform apply in bootstrap/
    └── Creates per-project SAs:
        ├── cs-my-pets-runtime   (Cloud Run/VM operations only)
        ├── cs-my-pets-deploy    (push images, deploy only)
        └── cs-my-pets-data      (BigQuery/Storage read-write only)
```

Result:

```
Organization
├── MY-SEED-PROJECT          control plane, no client resources
│   └── SA Orchestrator      creates infra but doesn't use it
│
└── my-pets                  client resources only
    ├── SA Runtime           runs apps
    ├── SA Deploy            deploys apps (via WIF, no keys)
    └── SA Data              reads/writes data
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `terraform apply` permission denied | ADC not configured | `gcloud auth application-default login` |
| Billing not linked | Billing on different account | Step 5 — manual `gcloud billing` command |
| `INVALID_PRINCIPAL` in deny policy | Wrong principal format | Must use `principal://iam.googleapis.com/projects/-/serviceAccounts/EMAIL` |
| VM uses wrong SA | VM created without `--service-account` | Delete and recreate VM via `install.sh` |
| Port 8000 in use | Old SSH tunnel still running | `kill $(lsof -ti:8000)` |
| Claude Desktop 307 redirect | Trailing slash in URL | Use `/mcp` not `/mcp/` |
| `ECONNREFUSED` in Claude Desktop | SSH tunnel not running | Restart the tunnel (Step 8) |
| SA hierarchy fails on project_create | Deny policy too restrictive | Ensure `deny_modify_critical_sas` only blocks delete/disable, not create |
| Env vars missing on VM | .env not updated after first boot | Step 7 |

## Stopping and restarting

**Stop the VM** (to save costs when not in use):
```bash
gcloud compute instances stop cloud-seed-vm \
  --zone=europe-west1-b --project=MY-SEED-PROJECT
```

**Start the VM** (Docker Compose auto-starts):
```bash
gcloud compute instances start cloud-seed-vm \
  --zone=europe-west1-b --project=MY-SEED-PROJECT
```

Then reconnect the tunnel (Step 8) and restart Claude Desktop.
