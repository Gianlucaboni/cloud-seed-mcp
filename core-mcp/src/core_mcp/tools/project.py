"""GCP project lifecycle management tools for the Core MCP server.

Creates new client projects, enables required APIs, prepares the
Terraform working directory, and provisions the per-project SA
hierarchy via the bootstrap Terraform module.

WIF (Workload Identity Federation) access is managed per-project
as an additive list — each entry creates a separate WIF provider,
allowing multiple GitHub identities to deploy to the same project.
"""

from __future__ import annotations

import json
import os
import textwrap

from mcp.server.fastmcp import FastMCP

from core_mcp.config import Settings
from core_mcp.tools._subprocess import run_command

# The WIF pool ID is a fixed constant — always created by bootstrap.
_WIF_POOL_ID = "cloudseed-github-pool"

# Default Artifact Registry repo name — one per project, shared by all images.
_AR_REPO_NAME = "cloud-seed-images"


def _build_wif_pool_name(project_number: str) -> str:
    """Construct the full WIF pool resource name from the seed project number."""
    return f"projects/{project_number}/locations/global/workloadIdentityPools/{_WIF_POOL_ID}"


# APIs that every client project needs.
_DEFAULT_APIS = [
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "sqladmin.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
]


def _read_client_projects(tfvars_path: str) -> dict:
    """Read existing client_projects from the projects tfvars JSON file.

    Returns a dict of {name: {project_id, github_access}}.
    """
    if not os.path.isfile(tfvars_path):
        return {}

    with open(tfvars_path) as f:
        try:
            data = json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}

    return data.get("client_projects", {})


def _write_projects_tfvars(
    tfvars_path: str,
    seed_project_id: str,
    org_id: str,
    wif_pool_name: str,
    client_projects: dict,
) -> None:
    """Write the projects.auto.tfvars.json file with updated client_projects.

    Uses JSON format (.auto.tfvars.json) which Terraform natively supports.
    """
    data = {
        "seed_project_id": seed_project_id,
        "org_id": org_id,
        "wif_pool_name": wif_pool_name,
        "client_projects": client_projects,
    }

    with open(tfvars_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def project_create(
        project_id: str,
        display_name: str = "",
        region: str = "europe-west1",
        billing_account_id: str = "",
        github_owner: str = "",
        tf_base_dir: str = "/opt/cloud-seed-mcp/projects",
    ) -> str:
        """Create a new GCP project with full SA hierarchy.

        This is a Yellow action.  Steps:
        1. Creates the GCP project under the organization via ``gcloud``.
        2. Links a billing account (required for most APIs).
        3. Enables default APIs (BigQuery, Storage, Cloud Run, etc.).
        4. Creates a Terraform working directory for the project's resources.
        5. Updates the bootstrap configuration and runs ``terraform apply``
           to create the per-project SA hierarchy (Runtime, Deploy, Data).

        The project is automatically configured with WIF access for the
        default GitHub owner (from CORE_MCP_GITHUB_OWNER env var). Use
        ``project_add_wif`` / ``project_remove_wif`` to modify access later.

        Args:
            project_id: Unique GCP project identifier (6-30 chars,
                        lowercase letters, digits, hyphens).
            display_name: Human-readable project name.
                          Defaults to *project_id* if empty.
            region: Default GCP region for resources.
            billing_account_id: GCP billing account ID to link.
                                If empty, the tool will attempt to find
                                the first available billing account.
            github_owner: GitHub account/org for WIF CI/CD access.
                          If empty, falls back to CORE_MCP_GITHUB_OWNER.
            tf_base_dir: Base directory for per-project Terraform dirs.
        """
        settings = Settings()
        if not display_name:
            display_name = project_id
        if not github_owner:
            github_owner = settings.github_owner

        lines: list[str] = []

        # ── 1. Create project ────────────────────────────────────────
        lines.append(f"[YELLOW ACTION] Creating GCP project '{project_id}'...")

        create_args = ["gcloud", "projects", "create", project_id,
                       f"--name={display_name}", "--quiet"]
        if settings.org_id:
            create_args.extend([f"--organization={settings.org_id}"])

        create_result = await run_command(*create_args)
        if not create_result.success:
            if "already exists" in create_result.stderr.lower() or "already in use" in create_result.stderr.lower():
                lines.append(f"Project '{project_id}' already exists — continuing.")
            else:
                return (
                    f"[YELLOW ACTION] Failed to create project '{project_id}'.\n"
                    f"stderr: {create_result.stderr}"
                )
        else:
            lines.append(f"Project '{project_id}' created.")

        # ── 2. Link billing ──────────────────────────────────────────
        if not billing_account_id:
            billing_result = await run_command(
                "gcloud", "billing", "accounts", "list",
                "--filter=open=true", "--format=value(ACCOUNT_ID)",
                "--limit=1",
            )
            if billing_result.success and billing_result.stdout.strip():
                billing_account_id = billing_result.stdout.strip()

        if billing_account_id:
            link_result = await run_command(
                "gcloud", "billing", "projects", "link", project_id,
                f"--billing-account={billing_account_id}",
                "--quiet",
            )
            if link_result.success:
                lines.append(f"Billing account {billing_account_id} linked.")
            else:
                lines.append(f"Warning: could not link billing — {link_result.stderr}")
        else:
            lines.append("Warning: no billing account found. APIs that require billing won't work.")

        # ── 2b. Remove auto-granted Owner role ────────────────────
        if settings.seed_project_id:
            orchestrator_sa = (
                f"cloudseed-orchestrator@{settings.seed_project_id}"
                ".iam.gserviceaccount.com"
            )
            remove_result = await run_command(
                "gcloud", "projects", "remove-iam-policy-binding", project_id,
                f"--member=serviceAccount:{orchestrator_sa}",
                "--role=roles/owner",
                "--quiet",
            )
            if remove_result.success:
                lines.append("Removed auto-granted Owner role from Orchestrator SA.")
            else:
                lines.append(
                    f"Warning: could not remove Owner role — {remove_result.stderr}"
                )

        # ── 3. Enable APIs ───────────────────────────────────────────
        enable_result = await run_command(
            "gcloud", "services", "enable", *_DEFAULT_APIS,
            f"--project={project_id}",
            "--quiet",
        )
        if enable_result.success:
            lines.append(f"Enabled {len(_DEFAULT_APIS)} APIs.")
        else:
            lines.append(f"Warning: some APIs may not have been enabled — {enable_result.stderr}")

        # ── 4. Prepare Terraform directory ───────────────────────────
        tf_dir = os.path.join(tf_base_dir, project_id)
        os.makedirs(tf_dir, exist_ok=True)

        provider_tf = textwrap.dedent(f"""\
            terraform {{
              required_providers {{
                google = {{
                  source  = "hashicorp/google"
                  version = "~> 5.0"
                }}
              }}
            }}

            provider "google" {{
              project = "{project_id}"
              region  = "{region}"
            }}
        """)
        provider_file = os.path.join(tf_dir, "provider.tf")
        with open(provider_file, "w") as f:
            f.write(provider_tf)

        lines.append(f"Terraform directory ready: {tf_dir}")

        # ── 5. Provision SA hierarchy via bootstrap/projects terraform ─
        projects_dir = settings.bootstrap_projects_dir
        tfvars_path = os.path.join(projects_dir, "projects.auto.tfvars.json")

        if not settings.seed_project_id or not settings.org_id:
            lines.append(
                "Warning: CORE_MCP_SEED_PROJECT_ID and CORE_MCP_ORG_ID not set. "
                "Skipping SA hierarchy provisioning. Set these env vars and retry."
            )
        elif not os.path.isdir(projects_dir):
            lines.append(
                f"Warning: projects directory '{projects_dir}' not found. "
                "Skipping SA hierarchy provisioning."
            )
        else:
            # Build WIF pool name from project number
            wif_pool_name = _build_wif_pool_name(settings.seed_project_number) if settings.seed_project_number else ""

            # Build github_access list with default owner
            github_access: list[dict] = []
            if github_owner:
                github_access.append({"type": "owner", "value": github_owner})

            # Read existing client projects, add the new one
            existing = _read_client_projects(tfvars_path)
            existing[project_id] = {
                "project_id": project_id,
                "github_access": github_access,
            }

            _write_projects_tfvars(
                tfvars_path,
                settings.seed_project_id,
                settings.org_id,
                wif_pool_name,
                existing,
            )
            lines.append("Updated projects.auto.tfvars.json with new client project.")

            # terraform init
            init_result = await run_command(
                "terraform", "init", "-input=false", "-no-color",
                cwd=projects_dir,
            )
            if not init_result.success:
                lines.append(f"Warning: terraform init failed — {init_result.stderr}")
            else:
                # terraform apply (auto-approve for SA provisioning)
                apply_result = await run_command(
                    "terraform", "apply",
                    "-input=false", "-no-color", "-auto-approve",
                    cwd=projects_dir,
                    timeout=300.0,
                )
                if apply_result.success:
                    lines.append(
                        "SA hierarchy provisioned: SA Runtime, SA Deploy, SA Data "
                        f"created for project '{project_id}'."
                    )
                    if github_owner and wif_pool_name:
                        lines.append(f"WIF access granted to GitHub owner '{github_owner}'.")

                    # ── 6. Create Artifact Registry repo ─────────────────
                    # Must happen AFTER terraform apply, which grants the
                    # Orchestrator editor role on the client project.
                    ar_result = await run_command(
                        "gcloud", "artifacts", "repositories", "create",
                        _AR_REPO_NAME,
                        "--repository-format=docker",
                        f"--location={region}",
                        f"--project={project_id}",
                        "--quiet",
                    )
                    if ar_result.success:
                        lines.append(f"Artifact Registry repo '{_AR_REPO_NAME}' created.")
                    elif "already exists" in ar_result.stderr.lower():
                        lines.append(f"Artifact Registry repo '{_AR_REPO_NAME}' already exists.")
                    else:
                        lines.append(f"Warning: could not create AR repo — {ar_result.stderr}")
                else:
                    lines.append(
                        f"Warning: terraform apply for SA hierarchy failed.\n"
                        f"stderr: {apply_result.stderr[:500]}"
                    )

        lines.append("")
        lines.append("Next steps:")
        lines.append(f"  - Use database_create_dataset with tf_dir='{tf_dir}'")
        lines.append(f"  - Use database_create_table to add tables")
        lines.append(f"  - Use terraform_plan and terraform_apply to provision resources")

        return "\n".join(lines)

    @mcp.tool()
    async def project_add_wif(
        project_id: str,
        access_type: str,
        access_value: str,
    ) -> str:
        """Add a GitHub identity that can deploy to a project via WIF.

        Each call adds a new WIF provider — multiple identities can deploy
        to the same project. Use ``project_remove_wif`` to revoke access.

        Examples:
          - Allow all repos from a GitHub user/org:
            ``project_add_wif(project_id="my-proj", access_type="owner", access_value="Gianlucaboni")``
          - Allow a specific repo only:
            ``project_add_wif(project_id="my-proj", access_type="repo", access_value="Gianlucaboni/my-repo")``

        This is a Yellow action.

        Args:
            project_id: GCP project identifier (must exist via ``project_create``).
            access_type: Either ``"owner"`` (all repos from an account/org)
                         or ``"repo"`` (a single repo in owner/repo format).
            access_value: The GitHub owner name or owner/repo string.
        """
        if access_type not in ("owner", "repo"):
            return "Error: access_type must be 'owner' or 'repo'."

        settings = Settings()

        if not settings.seed_project_id or not settings.org_id:
            return (
                "Error: CORE_MCP_SEED_PROJECT_ID and CORE_MCP_ORG_ID must be set. "
                "Cannot provision WIF without these."
            )

        if not settings.seed_project_number:
            return (
                "Error: CORE_MCP_SEED_PROJECT_NUMBER must be set. "
                "Cannot construct WIF pool name without the seed project number."
            )

        projects_dir = settings.bootstrap_projects_dir
        if not os.path.isdir(projects_dir):
            return f"Error: projects directory '{projects_dir}' not found."

        tfvars_path = os.path.join(projects_dir, "projects.auto.tfvars.json")
        wif_pool_name = _build_wif_pool_name(settings.seed_project_number)

        # Read existing projects and update github_access
        existing = _read_client_projects(tfvars_path)
        if project_id not in existing:
            existing[project_id] = {"project_id": project_id, "github_access": []}

        access_entry = {"type": access_type, "value": access_value}
        current_access = existing[project_id].get("github_access", [])

        # Check for duplicates
        if any(a["type"] == access_type and a["value"] == access_value for a in current_access):
            return (
                f"WIF access already exists for project '{project_id}': "
                f"{access_type}={access_value}. No changes made."
            )

        current_access.append(access_entry)
        existing[project_id]["github_access"] = current_access

        _write_projects_tfvars(
            tfvars_path,
            settings.seed_project_id,
            settings.org_id,
            wif_pool_name,
            existing,
        )

        # terraform init + apply
        init_result = await run_command(
            "terraform", "init", "-input=false", "-no-color",
            cwd=projects_dir,
        )
        if not init_result.success:
            return f"Error: terraform init failed — {init_result.stderr}"

        apply_result = await run_command(
            "terraform", "apply",
            "-input=false", "-no-color", "-auto-approve",
            cwd=projects_dir,
            timeout=300.0,
        )
        if not apply_result.success:
            return (
                f"Error: terraform apply failed.\n"
                f"stderr: {apply_result.stderr[:500]}"
            )

        # Build deploy SA email for output
        sa_prefix = f"cs-{project_id[:16]}"
        deploy_sa = f"{sa_prefix}-deploy@{settings.seed_project_id}.iam.gserviceaccount.com"

        lines = [
            f"[YELLOW ACTION] WIF access added for project '{project_id}'.",
            f"  Type: {access_type}",
            f"  Value: {access_value}",
            "",
            "GitHub Actions deploy workflow configuration:",
            f"  project_id: {project_id}",
            f"  service_account_email: {deploy_sa}",
            f"  workload_identity_provider: (check terraform output for full name)",
            f"  wif_pool: {wif_pool_name}",
            "",
            f"Current WIF access for this project ({len(current_access)} entries):",
        ]
        for a in current_access:
            lines.append(f"  - {a['type']}={a['value']}")

        return "\n".join(lines)

    @mcp.tool()
    async def project_remove_wif(
        project_id: str,
        access_type: str,
        access_value: str,
    ) -> str:
        """Remove a GitHub identity's deploy access from a project.

        Removes the WIF provider for the specified identity. Other
        identities' access is not affected.

        This is a Yellow action.

        Args:
            project_id: GCP project identifier.
            access_type: Either ``"owner"`` or ``"repo"``.
            access_value: The GitHub owner name or owner/repo string to remove.
        """
        if access_type not in ("owner", "repo"):
            return "Error: access_type must be 'owner' or 'repo'."

        settings = Settings()

        if not settings.seed_project_id or not settings.org_id:
            return "Error: CORE_MCP_SEED_PROJECT_ID and CORE_MCP_ORG_ID must be set."

        if not settings.seed_project_number:
            return "Error: CORE_MCP_SEED_PROJECT_NUMBER must be set."

        projects_dir = settings.bootstrap_projects_dir
        if not os.path.isdir(projects_dir):
            return f"Error: projects directory '{projects_dir}' not found."

        tfvars_path = os.path.join(projects_dir, "projects.auto.tfvars.json")
        wif_pool_name = _build_wif_pool_name(settings.seed_project_number)

        existing = _read_client_projects(tfvars_path)
        if project_id not in existing:
            return f"Error: project '{project_id}' not found in configuration."

        current_access = existing[project_id].get("github_access", [])
        new_access = [
            a for a in current_access
            if not (a["type"] == access_type and a["value"] == access_value)
        ]

        if len(new_access) == len(current_access):
            return (
                f"WIF entry not found for project '{project_id}': "
                f"{access_type}={access_value}. No changes made."
            )

        existing[project_id]["github_access"] = new_access

        _write_projects_tfvars(
            tfvars_path,
            settings.seed_project_id,
            settings.org_id,
            wif_pool_name,
            existing,
        )

        # terraform init + apply
        init_result = await run_command(
            "terraform", "init", "-input=false", "-no-color",
            cwd=projects_dir,
        )
        if not init_result.success:
            return f"Error: terraform init failed — {init_result.stderr}"

        apply_result = await run_command(
            "terraform", "apply",
            "-input=false", "-no-color", "-auto-approve",
            cwd=projects_dir,
            timeout=300.0,
        )
        if not apply_result.success:
            return (
                f"Error: terraform apply failed.\n"
                f"stderr: {apply_result.stderr[:500]}"
            )

        lines = [
            f"[YELLOW ACTION] WIF access removed for project '{project_id}'.",
            f"  Removed: {access_type}={access_value}",
            "",
        ]
        if new_access:
            lines.append(f"Remaining WIF access ({len(new_access)} entries):")
            for a in new_access:
                lines.append(f"  - {a['type']}={a['value']}")
        else:
            lines.append("No WIF access remains — GitHub Actions cannot deploy to this project.")

        return "\n".join(lines)

    @mcp.tool()
    async def project_list(org_only: bool = True) -> str:
        """List GCP projects.

        By default, lists only projects under the configured organization.
        Set ``org_only=False`` to list all accessible projects.

        This is a Green action (read-only).

        Args:
            org_only: If True, filter to projects under the configured org.
        """
        settings = Settings()

        args = ["gcloud", "projects", "list", "--format=json"]
        if org_only and settings.org_id:
            args.extend([f"--filter=parent.id={settings.org_id}"])

        result = await run_command(*args)
        if not result.success:
            return f"Error listing projects: {result.stderr}"

        try:
            projects = json.loads(result.stdout)
        except json.JSONDecodeError:
            return f"Error parsing output: {result.stdout}"

        if not projects:
            scope = f"organization {settings.org_id}" if org_only and settings.org_id else "this account"
            return f"No GCP projects found in {scope}."

        scope = f"organization {settings.org_id}" if org_only and settings.org_id else "all accessible"
        lines = [f"GCP projects in {scope} ({len(projects)}):"]
        for p in projects:
            pid = p.get("projectId", "unknown")
            name = p.get("name", "")
            state = p.get("lifecycleState", "")
            lines.append(f"  - {pid} ({name}) [{state}]")
        return "\n".join(lines)

    @mcp.tool()
    async def project_resources(
        project_id: str,
        tf_base_dir: str = "/opt/cloud-seed-mcp/projects",
    ) -> str:
        """List all resources defined or deployed for a project.

        Shows both the Terraform-declared resources (from .tf files) and
        the actually deployed resources (from terraform state).
        This is a Green action (read-only).

        Args:
            project_id: GCP project identifier.
            tf_base_dir: Base directory for per-project Terraform dirs.
        """
        tf_dir = os.path.join(tf_base_dir, project_id)

        if not os.path.isdir(tf_dir):
            return (
                f"No Terraform directory found for project '{project_id}' "
                f"at {tf_dir}. Has it been created with project_create?"
            )

        lines = [f"Resources for project '{project_id}':", f"Terraform dir: {tf_dir}", ""]

        # ── Declared resources (scan .tf files) ──────────────────────
        tf_files = sorted(
            f for f in os.listdir(tf_dir)
            if f.endswith(".tf") and f != "provider.tf"
        )

        if tf_files:
            lines.append(f"Declared in .tf files ({len(tf_files)}):")
            for tf_file in tf_files:
                filepath = os.path.join(tf_dir, tf_file)
                with open(filepath) as f:
                    content = f.read()

                # Extract resource types and names from HCL
                import re
                resources = re.findall(
                    r'resource\s+"(\S+)"\s+"(\S+)"',
                    content,
                )
                for rtype, rname in resources:
                    lines.append(f"  - {rtype}.{rname}  ({tf_file})")

                if not resources:
                    lines.append(f"  - {tf_file}  (no resource blocks)")
        else:
            lines.append("Declared: none (no .tf files besides provider.tf)")

        # ── Deployed resources (terraform state) ─────────────────────
        lines.append("")
        state_result = await run_command(
            "terraform", "state", "list",
            cwd=tf_dir,
        )

        if state_result.success and state_result.stdout.strip():
            resources = [r for r in state_result.stdout.splitlines() if r.strip()]
            lines.append(f"Deployed (in terraform state) ({len(resources)}):")
            for r in resources:
                lines.append(f"  - {r}")
        elif state_result.success:
            lines.append("Deployed: none (empty state — run terraform_apply to provision)")
        else:
            if "no state" in state_result.stderr.lower() or "does not exist" in state_result.stderr.lower():
                lines.append("Deployed: none (no terraform state file yet)")
            else:
                lines.append("Deployed: could not read state")

        return "\n".join(lines)
