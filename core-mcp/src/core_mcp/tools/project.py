"""GCP project lifecycle management tools for the Core MCP server.

Creates new client projects, enables required APIs, and prepares the
Terraform working directory for resource provisioning.
"""

from __future__ import annotations

import json
import os
import textwrap

from mcp.server.fastmcp import FastMCP

from core_mcp.tools._subprocess import run_command


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
]


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def project_create(
        project_id: str,
        display_name: str = "",
        region: str = "europe-west1",
        billing_account_id: str = "",
        tf_base_dir: str = "/opt/cloud-seed-mcp/projects",
    ) -> str:
        """Create a new GCP project and prepare it for resource provisioning.

        This is a Yellow action.  Steps:
        1. Creates the GCP project via ``gcloud``.
        2. Links a billing account (required for most APIs).
        3. Enables default APIs (BigQuery, Storage, Cloud Run, etc.).
        4. Creates a Terraform working directory with the provider
           configuration, ready for ``database_create_dataset`` and
           other resource tools.

        Args:
            project_id: Unique GCP project identifier (6-30 chars,
                        lowercase letters, digits, hyphens).
            display_name: Human-readable project name.
                          Defaults to *project_id* if empty.
            region: Default GCP region for resources.
            billing_account_id: GCP billing account ID to link.
                                If empty, the tool will attempt to find
                                the first available billing account.
            tf_base_dir: Base directory for per-project Terraform dirs.
                         A subdirectory ``<project_id>/`` is created
                         inside this path.
        """
        if not display_name:
            display_name = project_id

        lines: list[str] = []

        # ── 1. Create project ────────────────────────────────────────
        lines.append(f"[YELLOW ACTION] Creating GCP project '{project_id}'...")

        create_result = await run_command(
            "gcloud", "projects", "create", project_id,
            f"--name={display_name}",
            "--quiet",
        )
        if not create_result.success:
            if "already exists" in create_result.stderr.lower():
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
        lines.append(f"Provider configured for project '{project_id}', region '{region}'.")
        lines.append("")
        lines.append("Next steps:")
        lines.append(f"  - Use database_create_dataset with tf_dir='{tf_dir}' to create BigQuery datasets")
        lines.append(f"  - Use database_create_table to add tables")
        lines.append(f"  - Use terraform_plan and terraform_apply to provision resources")

        return "\n".join(lines)

    @mcp.tool()
    async def project_list() -> str:
        """List all GCP projects accessible to the current account.

        This is a Green action (read-only).
        """
        result = await run_command(
            "gcloud", "projects", "list",
            "--format=json",
        )
        if not result.success:
            return f"Error listing projects: {result.stderr}"

        try:
            projects = json.loads(result.stdout)
        except json.JSONDecodeError:
            return f"Error parsing output: {result.stdout}"

        if not projects:
            return "No GCP projects found."

        lines = [f"GCP projects ({len(projects)}):"]
        for p in projects:
            pid = p.get("projectId", "unknown")
            name = p.get("name", "")
            state = p.get("lifecycleState", "")
            lines.append(f"  - {pid} ({name}) [{state}]")
        return "\n".join(lines)
