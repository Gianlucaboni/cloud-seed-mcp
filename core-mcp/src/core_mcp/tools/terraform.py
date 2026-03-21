from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def terraform_plan(project_id: str, module_path: str) -> str:
        """Generate a Terraform plan for the specified module.

        Args:
            project_id: GCP project identifier
            module_path: Path to the Terraform module
        """
        return f"Plan generated for {project_id} at {module_path}"

    @mcp.tool()
    def terraform_apply(project_id: str, module_path: str) -> str:
        """Apply a Terraform plan after OPA validation.

        Args:
            project_id: GCP project identifier
            module_path: Path to the Terraform module
        """
        return f"Apply requested for {project_id} at {module_path} (requires approval)"

    @mcp.tool()
    def terraform_show_state(project_id: str) -> str:
        """Show current Terraform state for a project.

        Args:
            project_id: GCP project identifier
        """
        return f"State for {project_id}: (stub)"
