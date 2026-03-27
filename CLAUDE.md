# CLAUDE.md — Cloud Seed MCP

## Project Overview

Cloud Seed MCP is a self-evolving cloud agent delivered as an installable "seed" in a client's GCP environment. It targets small and medium businesses (SMBs) that need cloud infrastructure for projects ranging from IoT to data analytics but lack an internal DevOps team.

The product is based on the Model Context Protocol (MCP) and provides a conversational interface through which clients describe their needs. The system handles everything: infrastructure provisioning, code management, application deployment, and data management.

**Key differentiator:** The system self-evolves. It starts with a base set of tools and, when the client needs something that doesn't exist, generates new MCP tools autonomously — testing them through a staging pipeline before promoting to production.

---

## Architecture

### The Seed (docker-compose)

The seed is a Docker Compose package with 4 main containers:

1. **Core MCP Server** — The main orchestrator exposing base tools:
   - Terraform for infrastructure management
   - GitHub for repository and CI/CD management
   - Cloud Run for application deployment
   - Database management (Cloud SQL, Firestore, BigQuery)

2. **Policy Engine (OPA)** — Open Policy Agent server that validates every action against client policies before execution. Policies are written in Rego, are deterministic (not AI-dependent), and version-controlled in GitHub. Validates: budget, allowed regions, resource types, security requirements.

3. **Tool Forge** — Isolated environment for generating, testing, and validating new MCP tools. Pipeline: code generation + JSON schema → auto-generated unit tests → security scan → sandbox testing with ephemeral read-only SA → review → promotion to active registry.

4. **State Store** — Local PostgreSQL database maintaining a queryable view of the company state. Synchronized with authoritative sources: Terraform state (infrastructure), GitHub (code and decision history), gcloud (reality sanity check).

### State Management — Hybrid Approach

Authoritative sources of truth:
- **Terraform state** for declarative infrastructure
- **GitHub** for code, configuration, decision history
- **gcloud CLI** for real-state verification

The State Store is a synchronized cache layer for fast queries. Also holds the tool registry (custom tools, schemas, promotion status).

---

## Policy Engine (OPA)

- **What:** Open Policy Agent — open source, runs entirely locally as a Docker container
- **Port:** 8181 (internal to Docker network only)
- **Policies:** Written in Rego language, stored in `policies/` directory, versioned in GitHub
- **Integration:** Uses `conftest` or direct REST API to validate Terraform plan JSON

### Validation Flow

```
Core MCP generates Terraform plan
    → terraform plan -out=plan.tfplan
    → terraform show -json plan.tfplan
    → POST http://opa:8181/v1/data/terraform/deny (with plan JSON as input)
    → OPA returns array of violations (empty = all clear)
    → Core MCP proceeds or proposes alternatives
```

### Example Policies
- Max monthly budget per project
- Allowed regions (e.g., europe-west only)
- Allowed VM types (e.g., no GPU without explicit approval)
- Mandatory encryption on all buckets
- No publicly accessible resources
- Resource naming conventions

---

## Service Account Hierarchy — 4 Levels

### SA Installer
- Used ONLY during bootstrap
- Creates other SAs, configures base IAM policies
- **Disabled after installation** — never runs in production

### SA Orchestrator
- Lives in the "seed" project
- Operates on all client projects via Terraform + OPA validation
- Has explicit deny policies on destructive operations (delete project, modify critical IAM bindings)
- **Never acts without OPA validation**

### SA per-Project (one set per client project)
- **SA Runtime:** Used by Cloud Run services and VMs, minimal permissions for operation
- **SA Deploy:** Can push images and deploy, cannot touch infrastructure
- **SA Data:** Read/write on project buckets and databases, no infrastructure permissions
- **Created in the client project** (not the seed) — ensures Cloud Run can use the Runtime SA as service identity and provides natural structural isolation
- **Structural isolation:** IoT project SA cannot see Analytics project resources

### SA Ephemeral
- Created by Tool Forge for staging tools
- Live in the seed project
- Read-only permissions on target project
- TTL-based auto-destruction
- Cannot touch production

---

## Action Classification

### 🟢 Green (Autonomous)
- All read operations (list, describe, get)
- `terraform plan` (without apply)
- Code generation (without deployment)
- State Store queries
- Read-only data analysis

### 🟡 Yellow (Human Approval Required)
- `terraform apply` (creates new resources)
- Deployment on Cloud Run
- Database creation
- Tool promotion from staging to production
- Any operation above configurable cost threshold

### 🔴 Red (Always Blocked)
- GCP project deletion
- Modification of higher-level Service Accounts
- Disabling the policy engine
- Modifying OPA policies (only via git with review)
- Accessing credentials from other projects

---

## LLM Strategy — 3 Tiers

The Core MCP needs an LLM for interpreting requests, generating Terraform, and writing code for new tools. Three tiers available:

### Tier Essential (~300-600€/month)
- Remote API via Vertex AI
- Data stays within GCP infrastructure
- Simple, powerful, no GPU to manage

### Tier Secure (~450-700€/month)
- Hybrid: local model on T4 GPU for sensitive operations (data analysis, custom tool generation, state store queries)
- Remote API for generic operations (Terraform generation, CI/CD, architectural planning)
- Routing logic: if prompt contains client data → local; if abstract → remote

### Tier Air-gapped (~400-2200€/month)
- Full local, requires A100 GPU for comparable quality
- For organizations with extreme compliance requirements
- No data ever leaves the environment

**Architecture note:** The Core MCP doesn't change between tiers — only the inference layer swaps.

---

## CI/CD & Workload Identity Federation (WIF)

When the system creates a new project with GitHub-based CI/CD:

1. Creates GitHub repo with project scaffold
2. In client's GCP project creates:
   - `google_iam_workload_identity_pool` (accepts external identities)
   - `google_iam_workload_identity_pool_provider` (configured for GitHub OIDC)
   - `google_service_account` (SA Deploy with minimal permissions)
   - `google_service_account_iam_binding` (repo-specific binding)
3. Writes `.github/workflows/deploy.yml` with WIF auth
4. All via Terraform, all validated by OPA

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| IaC tool | Terraform | Industry standard, JSON plan output for OPA validation |
| Policy engine | OPA (Rego) | Open source, vendor-neutral, deterministic |
| Packaging | Docker Compose | Simple for SMBs, upgradeable to K8s |
| State store | PostgreSQL | Robust, queryable, well-understood |
| VCS | GitHub | Actions ecosystem, native WIF with GCP |
| Cloud provider | GCP | Initial target, multi-cloud is a future expansion |

---

## Open Issues

1. **MCP Client:** How does the client interact with the system? Claude Desktop, custom web UI, CLI?
2. **Human approval mechanism:** Configurable thresholds, interaction UX (notifications, communication channel)
3. **Testing auto-generated tools on real data:** Read-only copy? Synthetic data? Controlled subset?
4. **Bootstrap experience:** Time from installation to operability, degree of automation
5. **Business model:** SaaS fee, consulting, tier-based pricing
6. **Vertex AI integration:** Implementation details for Tier Essential
7. **Monitoring & observability:** How the client monitors the system and costs in real-time

---

## Development Guidelines

- **GitHub:** Always use GitHub MCP tools (mcp__github__*) for all GitHub operations (issues, PRs, repos). Never use `gh` CLI via Bash.
- **Language:** Python for Core MCP and tool generation (Go for future performance-critical components)
- **Terraform:** All infrastructure changes MUST go through Terraform — no manual gcloud operations
- **OPA validation:** Every Terraform plan MUST pass OPA validation before apply — no exceptions
- **SA principle:** Least privilege always. Every SA gets the minimum permissions needed.
- **Git:** Everything in git. Infrastructure, policies, tool code, schemas, configuration.
- **Testing:** Auto-generated tools must pass unit tests, security scan, and sandbox test before promotion
- **Docker:** All components containerized, all communication via internal Docker network
- **No secrets in code:** SA keys via Workload Identity or Secret Manager, never hardcoded

---

## Project Structure (Target)

```
cloud-seed-mcp/
├── docker-compose.yml
├── core-mcp/
│   ├── server.py              # Main MCP server
│   ├── tools/
│   │   ├── terraform.py       # Terraform tool
│   │   ├── github.py          # GitHub tool
│   │   ├── cloudrun.py        # Cloud Run deploy tool
│   │   └── database.py        # Database management tool
│   └── llm/
│       ├── interface.py       # Abstract LLM interface
│       ├── vertex.py          # Vertex AI implementation
│       ├── anthropic.py       # Anthropic API implementation
│       └── local.py           # Local model implementation
├── policy-engine/
│   ├── policies/
│   │   ├── budget.rego
│   │   ├── regions.rego
│   │   ├── resources.rego
│   │   └── security.rego
│   └── conftest/
├── tool-forge/
│   ├── generator.py           # Tool code generator
│   ├── tester.py              # Auto test generator and runner
│   ├── scanner.py             # Security scanner
│   ├── sandbox.py             # Sandbox environment manager
│   └── registry.py            # Tool registry manager
├── state-store/
│   ├── schema.sql
│   ├── sync/
│   │   ├── terraform_sync.py
│   │   ├── github_sync.py
│   │   └── gcloud_sync.py
│   └── api/
├── bootstrap/
│   ├── install.sh             # VM startup script
│   ├── sa_hierarchy.tf        # SA creation Terraform
│   └── discovery.py           # Existing infra discovery
├── templates/
│   ├── terraform/             # Terraform module templates
│   ├── github-workflows/      # CI/CD workflow templates
│   └── tools/                 # Tool scaffold templates
└── docs/
```