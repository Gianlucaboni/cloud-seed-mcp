"""Cloud Run CLI tool wrappers for the Core MCP server."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from core_mcp.tools._subprocess import run_command


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def cloudrun_deploy(
        project_id: str,
        service_name: str,
        image: str,
        region: str = "europe-west1",
    ) -> str:
        """Deploy a service to Cloud Run.

        Uses ``gcloud run deploy``.  This is a Yellow action (creates /
        updates infrastructure).

        Args:
            project_id: GCP project identifier.
            service_name: Name of the Cloud Run service.
            image: Docker image URI (e.g. ``gcr.io/project/image:tag``).
            region: GCP region for deployment.
        """
        result = await run_command(
            "gcloud", "run", "deploy", service_name,
            f"--image={image}",
            f"--project={project_id}",
            f"--region={region}",
            "--platform=managed",
            "--no-allow-unauthenticated",
            "--quiet",
            "--format=json",
            timeout=600.0,
        )

        if not result.success:
            return (
                f"[YELLOW ACTION] Cloud Run deployment failed for "
                f"'{service_name}' in project '{project_id}'.\n"
                f"stderr: {result.stderr}"
            )

        # Try to parse the JSON output for a nice summary
        try:
            svc = json.loads(result.stdout)
            url = svc.get("status", {}).get("url", "N/A")
            revision = svc.get("status", {}).get("latestReadyRevisionName", "N/A")
            return (
                f"[YELLOW ACTION] Cloud Run deployment succeeded.\n"
                f"Service: {service_name}\n"
                f"Project: {project_id}\n"
                f"Region: {region}\n"
                f"Image: {image}\n"
                f"URL: {url}\n"
                f"Latest revision: {revision}"
            )
        except json.JSONDecodeError:
            return (
                f"[YELLOW ACTION] Cloud Run deployment completed for "
                f"'{service_name}' in project '{project_id}'.\n"
                f"Output:\n{result.stdout[:2000]}"
            )

    @mcp.tool()
    async def cloudrun_list_services(
        project_id: str,
        region: str = "europe-west1",
    ) -> str:
        """List Cloud Run services in a project.

        This is a Green action (read-only).

        Args:
            project_id: GCP project identifier.
            region: GCP region to list services from.
        """
        result = await run_command(
            "gcloud", "run", "services", "list",
            f"--project={project_id}",
            f"--region={region}",
            "--platform=managed",
            "--format=json",
        )

        if not result.success:
            return (
                f"Failed to list Cloud Run services in project '{project_id}' "
                f"({region}).\nstderr: {result.stderr}"
            )

        try:
            services = json.loads(result.stdout)
        except json.JSONDecodeError:
            return (
                f"Failed to parse service list.\n"
                f"Raw output:\n{result.stdout[:2000]}"
            )

        if not services:
            return (
                f"No Cloud Run services found in project '{project_id}' "
                f"({region})."
            )

        lines = [
            f"Cloud Run services in '{project_id}' ({region}):",
            f"Total: {len(services)}",
            "",
        ]
        for svc in services:
            name = svc.get("metadata", {}).get("name", "unknown")
            url = svc.get("status", {}).get("url", "N/A")
            ready = "yes"
            conditions = svc.get("status", {}).get("conditions", [])
            for cond in conditions:
                if cond.get("type") == "Ready":
                    ready = "yes" if cond.get("status") == "True" else "no"
                    break
            lines.append(f"  - {name}")
            lines.append(f"    URL: {url}")
            lines.append(f"    Ready: {ready}")

        return "\n".join(lines)
