# Cloud Seed MCP

A self-evolving cloud agent delivered as an installable "seed" in a client's GCP environment. Built on the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), it provides a conversational interface for infrastructure provisioning, code management, application deployment, and data management — targeting small and medium businesses (SMBs) that lack an internal DevOps team.

**Key differentiator:** The system self-evolves. It starts with a base set of tools and, when a client needs something that doesn't exist, generates new MCP tools autonomously — testing them through a staging pipeline before promoting to production.

## Architecture

The seed is a Docker Compose package with 4 containers running on an internal network:

```
┌───────────────────────────────────────────────────────┐
│                    seed-net (bridge)                   │
│                                                       │
│  ┌───────────┐  ┌──────┐  ┌────────────┐  ┌────────┐ │
│  │  Core MCP │  │  OPA │  │ Tool Forge │  │ State  │ │
│  │  :8000    │  │ :8181│  │            │  │ Store  │ │
│  │  (Python) │→ │(Rego)│  │  (Python)  │  │ :5432  │ │
│  └───────────┘  └──────┘  └────────────┘  │(Postgres)││
│       ↑ only port exposed to host         └────────┘ │
└───────────────────────────────────────────────────────┘
```

| Container | Role |
|-----------|------|
| **Core MCP Server** | Main orchestrator exposing tools for Terraform, GitHub, Cloud Run, and database management via MCP protocol |
| **Policy Engine (OPA)** | Open Policy Agent validating every Terraform plan against budget, region, resource, and security policies |
| **Tool Forge** | Generates, tests, scans, and promotes new MCP tools autonomously |
| **State Store** | PostgreSQL database maintaining a queryable view of infrastructure state, tool registry, and audit logs |

## Quick Start

```bash
# Clone
git clone https://github.com/Gianlucaboni/cloud-seed-mcp.git
cd cloud-seed-mcp

# Configure
cp .env.example .env
# Edit .env with your settings

# Start all services
docker compose up -d

# Verify
docker compose ps
curl http://localhost:8000/mcp  # Core MCP server
```

## Project Structure

```
cloud-seed-mcp/
├── docker-compose.yml          # 4 services on seed-net
├── .env.example                # Environment variables template
├── core-mcp/                   # Core MCP Server
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/core_mcp/
│       ├── server.py           # FastMCP server (11 tools registered)
│       ├── config.py           # Settings via CORE_MCP_ env vars
│       └── tools/
│           ├── _subprocess.py  # Async CLI wrapper (shared helper)
│           ├── terraform.py    # terraform init/plan/apply/show + OPA validation
│           ├── github.py       # gh repo create/list, git push
│           ├── cloudrun.py     # gcloud run deploy/list
│           └── database.py     # BigQuery + Cloud SQL via Terraform HCL generation
├── policy-engine/              # OPA Policy Engine
│   ├── Dockerfile
│   ├── opa-config.yaml
│   ├── policies/
│   │   ├── budget.rego         # Monthly cost limits (default 500 EUR)
│   │   ├── regions.rego        # Allowed regions (default: europe-west)
│   │   ├── resources.rego      # Resource type whitelist + GPU controls
│   │   └── security.rego       # Encryption, no public access, naming
│   ├── data/defaults.json      # Configurable policy values
│   └── tests/                  # OPA test suite + JSON fixtures
├── tool-forge/                 # Tool Forge Pipeline
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/tool_forge/
│       ├── generator.py        # Template-based MCP tool code generation
│       ├── tester.py           # Auto-generated pytest runner
│       ├── scanner.py          # AST-based security scanner
│       ├── sandbox.py          # Isolated execution environment
│       ├── registry.py         # PostgreSQL tool registry (staging → active)
│       └── templates/          # Jinja2 templates for code generation
├── state-store/                # PostgreSQL State Store
│   └── init/01-schema.sql      # Schema: projects, resources, tool_registry, logs
├── bootstrap/                  # GCP Bootstrap & SA Hierarchy
│   ├── install.sh              # One-time bootstrap script
│   ├── sa_hierarchy.tf         # 4-level Service Account hierarchy
│   ├── deny_policy.tf          # IAM deny policies for Orchestrator
│   └── modules/
│       ├── project_sa/         # Per-project SAs (Runtime, Deploy, Data)
│       └── ephemeral_sa/       # TTL-based read-only SAs for sandbox
└── CLAUDE.md                   # Full architecture specification
```

## How It Works

### Example: "Save my IoT sensor data to a new database"

1. **User** sends the request via MCP client
2. **Core MCP** calls `database_create_dataset` → generates Terraform HCL → runs `terraform plan`
3. **Core MCP** calls `terraform_apply` → reads plan JSON → sends to **OPA** for validation
4. **OPA** evaluates all 4 policies (budget, region, resources, security) → returns violations or empty array
5. If OPA approves → `terraform apply` creates the BigQuery dataset on GCP
6. Response returned to the user with details

### Action Classification

| Level | Actions | Behavior |
|-------|---------|----------|
| **Green** | Read operations, `terraform plan`, listing resources | Executes directly |
| **Yellow** | `terraform apply`, deployments, database creation | Requires human approval |
| **Red** | Project deletion, SA modification, disabling OPA | Always blocked |

### Self-Evolving Tools

When a client needs a tool that doesn't exist:

1. **Tool Forge** generates Python code following the MCP tool pattern
2. Auto-generated **pytest tests** validate the tool
3. **AST-based security scanner** checks for dangerous patterns (eval, subprocess, unauthorized network)
4. **Sandbox** executes the tool in isolation with restricted environment
5. If all gates pass → tool is **promoted** to the active registry

## Service Account Hierarchy

4-level least-privilege model:

| Level | SA | Purpose | Lifecycle |
|-------|-----|---------|-----------|
| 1 | **Installer** | Creates all other SAs during bootstrap | Disabled after install |
| 2 | **Orchestrator** | Day-to-day operations via Terraform + OPA | Permanent, with deny policies |
| 3 | **Per-Project** | Runtime, Deploy, Data SAs per client project | Created per project |
| 4 | **Ephemeral** | Read-only SAs for Tool Forge sandbox testing | TTL-based auto-cleanup |

## Development

### Core MCP Tests
```bash
cd core-mcp && uv sync --dev && uv run pytest -v
# 64 tests
```

### OPA Policy Tests
```bash
brew install opa  # if not installed
opa test policy-engine/policies/ policy-engine/tests/ --ignore '*.json' -v
# 24 tests
```

### Tool Forge Tests
```bash
cd tool-forge && uv sync --dev && uv run pytest -v
# 59 tests
```

## Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| IaC | Terraform | Industry standard, JSON plan output for OPA |
| Policy Engine | OPA (Rego) | Open source, vendor-neutral, deterministic |
| Packaging | Docker Compose | Simple for SMBs, upgradeable to K8s |
| State Store | PostgreSQL | Robust, queryable |
| VCS | GitHub | Actions ecosystem, native WIF with GCP |
| Cloud | GCP | Initial target, multi-cloud planned |
| Language | Python | Core MCP and tool generation |

## License

Private — not yet licensed for distribution.
