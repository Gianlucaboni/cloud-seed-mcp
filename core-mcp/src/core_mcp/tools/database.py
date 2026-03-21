"""Database management tool wrappers for the Core MCP server.

BigQuery datasets and Cloud SQL instances are managed via Terraform HCL
generation followed by terraform plan/apply.  Listing uses ``gcloud`` CLI
directly.
"""

from __future__ import annotations

import json
import os
import textwrap

from mcp.server.fastmcp import FastMCP

from core_mcp.tools._subprocess import run_command


def _write_bigquery_hcl(
    tf_dir: str,
    project_id: str,
    dataset_id: str,
    location: str,
) -> str:
    """Write a minimal Terraform file for a BigQuery dataset.

    Returns the path to the written .tf file.
    """
    hcl = textwrap.dedent(f"""\
        provider "google" {{
          project = "{project_id}"
        }}

        resource "google_bigquery_dataset" "{dataset_id}" {{
          dataset_id = "{dataset_id}"
          location   = "{location}"

          labels = {{
            managed_by = "cloud-seed"
          }}
        }}
    """)
    os.makedirs(tf_dir, exist_ok=True)
    tf_file = os.path.join(tf_dir, f"bigquery_{dataset_id}.tf")
    with open(tf_file, "w") as f:
        f.write(hcl)
    return tf_file


def _write_cloudsql_hcl(
    tf_dir: str,
    project_id: str,
    instance_name: str,
    region: str,
    db_version: str = "POSTGRES_15",
    tier: str = "db-f1-micro",
) -> str:
    """Write a minimal Terraform file for a Cloud SQL instance.

    Returns the path to the written .tf file.
    """
    hcl = textwrap.dedent(f"""\
        provider "google" {{
          project = "{project_id}"
        }}

        resource "google_sql_database_instance" "{instance_name}" {{
          name             = "{instance_name}"
          database_version = "{db_version}"
          region           = "{region}"

          settings {{
            tier = "{tier}"
          }}

          deletion_protection = true

          labels = {{
            managed_by = "cloud-seed"
          }}
        }}
    """)
    os.makedirs(tf_dir, exist_ok=True)
    tf_file = os.path.join(tf_dir, f"cloudsql_{instance_name}.tf")
    with open(tf_file, "w") as f:
        f.write(hcl)
    return tf_file


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def database_create_dataset(
        project_id: str,
        dataset_id: str,
        location: str = "EU",
        tf_dir: str = "",
    ) -> str:
        """Create a BigQuery dataset via Terraform.

        Generates Terraform HCL, runs ``terraform init`` and
        ``terraform plan``.  This is a Yellow action -- actual creation
        requires approval via ``terraform_apply``.

        Args:
            project_id: GCP project identifier.
            dataset_id: BigQuery dataset identifier.
            location: Dataset location (e.g. ``EU``, ``US``).
            tf_dir: Absolute path to the Terraform working directory.
                    If empty, returns an error.
        """
        if not tf_dir:
            return "Error: tf_dir is required (absolute path to Terraform working directory)."

        if not os.path.isabs(tf_dir):
            return f"Error: tf_dir must be an absolute path, got: {tf_dir}"

        # Generate Terraform HCL
        tf_file = _write_bigquery_hcl(tf_dir, project_id, dataset_id, location)

        # terraform init
        init_result = await run_command(
            "terraform", "init", "-input=false", "-no-color",
            cwd=tf_dir,
        )
        if not init_result.success:
            return (
                f"[YELLOW ACTION] Terraform init failed.\n"
                f"stderr: {init_result.stderr}"
            )

        # terraform plan
        plan_file = os.path.join(tf_dir, "plan.tfplan")
        plan_result = await run_command(
            "terraform", "plan",
            "-input=false", "-no-color",
            f"-out={plan_file}",
            cwd=tf_dir,
        )
        if not plan_result.success:
            return (
                f"[YELLOW ACTION] Terraform plan failed for BigQuery dataset "
                f"'{dataset_id}'.\nstderr: {plan_result.stderr}"
            )

        return (
            f"[YELLOW ACTION] BigQuery dataset '{dataset_id}' Terraform plan "
            f"generated successfully.\n"
            f"Project: {project_id}\n"
            f"Location: {location}\n"
            f"HCL file: {tf_file}\n"
            f"Plan file: {plan_file}\n\n"
            f"Run terraform_apply to create the dataset (requires approval)."
        )

    @mcp.tool()
    async def database_create_instance(
        project_id: str,
        instance_name: str,
        db_type: str = "cloud-sql",
        region: str = "europe-west1",
        tf_dir: str = "",
    ) -> str:
        """Create a database instance (Cloud SQL) via Terraform.

        Generates Terraform HCL, runs ``terraform init`` and
        ``terraform plan``.  This is a Yellow action -- actual creation
        requires approval via ``terraform_apply``.

        Args:
            project_id: GCP project identifier.
            instance_name: Database instance name.
            db_type: Database type. Currently supports ``cloud-sql``.
            region: GCP region.
            tf_dir: Absolute path to the Terraform working directory.
        """
        if not tf_dir:
            return "Error: tf_dir is required (absolute path to Terraform working directory)."

        if not os.path.isabs(tf_dir):
            return f"Error: tf_dir must be an absolute path, got: {tf_dir}"

        if db_type not in ("cloud-sql",):
            return (
                f"Error: unsupported db_type '{db_type}'. "
                f"Currently supported: cloud-sql."
            )

        tf_file = _write_cloudsql_hcl(tf_dir, project_id, instance_name, region)

        # terraform init
        init_result = await run_command(
            "terraform", "init", "-input=false", "-no-color",
            cwd=tf_dir,
        )
        if not init_result.success:
            return (
                f"[YELLOW ACTION] Terraform init failed.\n"
                f"stderr: {init_result.stderr}"
            )

        # terraform plan
        plan_file = os.path.join(tf_dir, "plan.tfplan")
        plan_result = await run_command(
            "terraform", "plan",
            "-input=false", "-no-color",
            f"-out={plan_file}",
            cwd=tf_dir,
        )
        if not plan_result.success:
            return (
                f"[YELLOW ACTION] Terraform plan failed for Cloud SQL "
                f"instance '{instance_name}'.\nstderr: {plan_result.stderr}"
            )

        return (
            f"[YELLOW ACTION] Cloud SQL instance '{instance_name}' Terraform "
            f"plan generated successfully.\n"
            f"Project: {project_id}\n"
            f"Region: {region}\n"
            f"HCL file: {tf_file}\n"
            f"Plan file: {plan_file}\n\n"
            f"Run terraform_apply to create the instance (requires approval)."
        )

    @mcp.tool()
    async def database_list_databases(project_id: str) -> str:
        """List all database resources in a project.

        Queries BigQuery datasets and Cloud SQL instances via ``gcloud``.
        This is a Green action (read-only).

        Args:
            project_id: GCP project identifier.
        """
        sections: list[str] = [f"Database resources in project '{project_id}':\n"]

        # --- BigQuery datasets ---
        bq_result = await run_command(
            "gcloud", "alpha", "bq", "datasets", "list",
            f"--project={project_id}",
            "--format=json",
        )
        if bq_result.success:
            try:
                datasets = json.loads(bq_result.stdout)
                if datasets:
                    sections.append(f"BigQuery datasets ({len(datasets)}):")
                    for ds in datasets:
                        ds_id = ds.get("datasetReference", {}).get("datasetId", "unknown")
                        loc = ds.get("location", "unknown")
                        sections.append(f"  - {ds_id} (location: {loc})")
                else:
                    sections.append("BigQuery datasets: none")
            except json.JSONDecodeError:
                sections.append(f"BigQuery: failed to parse output")
        else:
            # Fallback: try bq ls
            bq_alt = await run_command(
                "bq", "ls",
                f"--project_id={project_id}",
                "--format=json",
            )
            if bq_alt.success:
                try:
                    datasets = json.loads(bq_alt.stdout)
                    if datasets:
                        sections.append(f"BigQuery datasets ({len(datasets)}):")
                        for ds in datasets:
                            ds_id = ds.get("datasetReference", {}).get("datasetId", "unknown")
                            sections.append(f"  - {ds_id}")
                    else:
                        sections.append("BigQuery datasets: none")
                except json.JSONDecodeError:
                    sections.append("BigQuery: unable to list datasets")
            else:
                sections.append(
                    f"BigQuery: unable to list datasets "
                    f"({bq_result.stderr or bq_alt.stderr})"
                )

        # --- Cloud SQL instances ---
        sql_result = await run_command(
            "gcloud", "sql", "instances", "list",
            f"--project={project_id}",
            "--format=json",
        )
        if sql_result.success:
            try:
                instances = json.loads(sql_result.stdout)
                if instances:
                    sections.append(f"\nCloud SQL instances ({len(instances)}):")
                    for inst in instances:
                        name = inst.get("name", "unknown")
                        db_ver = inst.get("databaseVersion", "unknown")
                        state = inst.get("state", "unknown")
                        region = inst.get("region", "unknown")
                        sections.append(
                            f"  - {name} ({db_ver}) [{state}] in {region}"
                        )
                else:
                    sections.append("\nCloud SQL instances: none")
            except json.JSONDecodeError:
                sections.append("\nCloud SQL: failed to parse output")
        else:
            sections.append(
                f"\nCloud SQL: unable to list instances ({sql_result.stderr})"
            )

        return "\n".join(sections)
