from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def cloudrun_deploy(
        project_id: str,
        service_name: str,
        image: str,
        region: str = "europe-west1",
    ) -> str:
        """Deploy a service to Cloud Run.

        Args:
            project_id: GCP project identifier
            service_name: Name of the Cloud Run service
            image: Docker image URI (e.g. gcr.io/project/image:tag)
            region: GCP region for deployment
        """
        return f"Deploying {image} as {service_name} in {project_id} ({region})"

    @mcp.tool()
    def cloudrun_list_services(project_id: str, region: str = "europe-west1") -> str:
        """List Cloud Run services in a project.

        Args:
            project_id: GCP project identifier
            region: GCP region to list services from
        """
        return f"Services in {project_id} ({region}): (stub)"
