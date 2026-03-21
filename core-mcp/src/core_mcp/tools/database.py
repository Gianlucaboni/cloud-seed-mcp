from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def database_create_dataset(
        project_id: str, dataset_id: str, location: str = "EU"
    ) -> str:
        """Create a BigQuery dataset.

        Args:
            project_id: GCP project identifier
            dataset_id: BigQuery dataset identifier
            location: Dataset location
        """
        return f"BigQuery dataset '{dataset_id}' created in {project_id} ({location})"

    @mcp.tool()
    def database_create_instance(
        project_id: str,
        instance_name: str,
        db_type: str = "cloud-sql",
        region: str = "europe-west1",
    ) -> str:
        """Create a database instance (Cloud SQL or Firestore).

        Args:
            project_id: GCP project identifier
            instance_name: Database instance name
            db_type: Database type (cloud-sql, firestore)
            region: GCP region
        """
        return f"Database instance '{instance_name}' ({db_type}) created in {project_id} ({region})"

    @mcp.tool()
    def database_list_databases(project_id: str) -> str:
        """List all database resources in a project.

        Args:
            project_id: GCP project identifier
        """
        return f"Databases in {project_id}: (stub)"
