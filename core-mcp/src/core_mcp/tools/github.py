from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def github_create_repo(name: str, description: str = "", private: bool = True) -> str:
        """Create a new GitHub repository for a project.

        Args:
            name: Repository name
            description: Repository description
            private: Whether the repository should be private
        """
        return f"Repository '{name}' created (private={private})"

    @mcp.tool()
    def github_list_repos() -> str:
        """List all GitHub repositories managed by Cloud Seed."""
        return "Repositories: (stub)"

    @mcp.tool()
    def github_push_files(repo: str, branch: str, files: list[str], message: str) -> str:
        """Push files to a GitHub repository.

        Args:
            repo: Repository name (owner/repo)
            branch: Target branch
            files: List of file paths to push
            message: Commit message
        """
        return f"Pushed {len(files)} files to {repo}:{branch}"
