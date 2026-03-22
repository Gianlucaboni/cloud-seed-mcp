"""GitHub / git CLI tool wrappers for the Core MCP server."""

from __future__ import annotations

import json
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from mcp.server.fastmcp import FastMCP

from core_mcp.config import Settings
from core_mcp.tools._subprocess import run_command


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def github_create_repo(
        name: str,
        description: str = "",
        private: bool = True,
    ) -> str:
        """Create a new GitHub repository for a project.

        Uses the ``gh`` CLI.  This is a Yellow action (creates a resource).

        Args:
            name: Repository name (e.g. ``my-project``).
            description: Optional repository description.
            private: Whether the repository should be private.
        """
        args = ["gh", "repo", "create", name]
        if private:
            args.append("--private")
        else:
            args.append("--public")

        if description:
            args.extend(["--description", description])

        # Add default options
        args.append("--confirm")

        result = await run_command(*args)

        if not result.success:
            return (
                f"[YELLOW ACTION] Failed to create repository '{name}'.\n"
                f"stderr: {result.stderr}"
            )

        return (
            f"[YELLOW ACTION] Repository '{name}' created successfully.\n"
            f"Visibility: {'private' if private else 'public'}\n"
            f"URL: {result.stdout}"
        )

    @mcp.tool()
    async def github_list_repos(org: str = "") -> str:
        """List GitHub repositories managed by Cloud Seed.

        This is a Green action (read-only).

        Args:
            org: Optional GitHub organization.  If empty, lists repos for the
                 authenticated user.
        """
        args = ["gh", "repo", "list"]
        if org:
            args = ["gh", "repo", "list", org]

        args.extend(["--json", "name,description,visibility,updatedAt", "--limit", "50"])

        result = await run_command(*args)

        if not result.success:
            return f"Failed to list repositories.\nstderr: {result.stderr}"

        try:
            repos = json.loads(result.stdout)
        except json.JSONDecodeError:
            return f"Failed to parse repository list.\nRaw output:\n{result.stdout[:2000]}"

        if not repos:
            return "No repositories found."

        lines = [f"Repositories ({len(repos)}):"]
        for repo in repos:
            vis = repo.get("visibility", "unknown")
            desc = repo.get("description") or "(no description)"
            updated = repo.get("updatedAt", "unknown")
            lines.append(f"  - {repo['name']} [{vis}] updated {updated}")
            lines.append(f"    {desc}")

        return "\n".join(lines)

    @mcp.tool()
    async def github_push_files(
        repo: str,
        branch: str,
        files: list[str],
        message: str,
        work_dir: str = "",
    ) -> str:
        """Push files to a GitHub repository.

        Uses ``git`` CLI to add, commit, and push.  The caller must provide a
        local working directory that is already a git clone of the repo.
        This is a Yellow action (modifies remote state).

        Args:
            repo: Repository name (owner/repo).
            branch: Target branch.
            files: List of file paths (relative to work_dir) to add.
            message: Commit message.
            work_dir: Absolute path to the local git clone.
        """
        if not work_dir:
            return "Error: work_dir is required (absolute path to a local git clone)."

        if not os.path.isabs(work_dir):
            return f"Error: work_dir must be an absolute path, got: {work_dir}"

        if not files:
            return "Error: files list is empty, nothing to push."

        # --- git checkout / create branch ---
        checkout_result = await run_command(
            "git", "checkout", "-B", branch,
            cwd=work_dir,
        )
        if not checkout_result.success:
            return (
                f"Failed to checkout branch '{branch}'.\n"
                f"stderr: {checkout_result.stderr}"
            )

        # --- git add ---
        add_result = await run_command(
            "git", "add", *files,
            cwd=work_dir,
        )
        if not add_result.success:
            return (
                f"Failed to stage files.\n"
                f"stderr: {add_result.stderr}"
            )

        # --- git commit ---
        commit_result = await run_command(
            "git", "commit", "-m", message,
            cwd=work_dir,
        )
        if not commit_result.success:
            # "nothing to commit" is not really an error
            if "nothing to commit" in commit_result.stdout.lower():
                return "No changes to commit. Files are already up to date."
            return (
                f"Failed to commit.\n"
                f"stderr: {commit_result.stderr}\n"
                f"stdout: {commit_result.stdout}"
            )

        # --- git push ---
        push_result = await run_command(
            "git", "push", "-u", "origin", branch,
            cwd=work_dir,
        )
        if not push_result.success:
            return (
                f"[YELLOW ACTION] Commit succeeded but push failed.\n"
                f"stderr: {push_result.stderr}"
            )

        return (
            f"[YELLOW ACTION] Pushed {len(files)} file(s) to {repo}:{branch}.\n"
            f"Commit: {message}\n"
            f"Output: {push_result.stderr or push_result.stdout}"
        )

    @mcp.tool()
    async def github_setup_cicd(
        repo: str,
        project_id: str,
        service_name: str,
        service_account_email: str,
        workload_identity_provider: str,
        region: str = "europe-west1",
        work_dir: str = "",
    ) -> str:
        """Set up GitHub Actions CI/CD with Workload Identity Federation.

        Generates a deploy.yml workflow that authenticates via WIF (no SA keys)
        and deploys to Cloud Run on push to main.  This is a Yellow action.

        Args:
            repo: GitHub repository (owner/repo format).
            project_id: GCP project identifier for deployment target.
            service_name: Cloud Run service name.
            service_account_email: SA Deploy email for WIF authentication.
            workload_identity_provider: Full WIF provider resource name.
            region: GCP region for deployment.
            work_dir: Absolute path to the local git clone of the repo.
        """
        if not work_dir:
            return "Error: work_dir is required (absolute path to the local git clone)."

        if not os.path.isabs(work_dir):
            return f"Error: work_dir must be an absolute path, got: {work_dir}"

        # Render workflow template
        settings = Settings()
        templates_path = Path(settings.templates_dir) / "github-workflows"

        if not templates_path.is_dir():
            return f"Error: templates directory not found at {templates_path}"

        env = Environment(
            loader=FileSystemLoader(str(templates_path)),
            keep_trailing_newline=True,
        )
        template = env.get_template("deploy.yml.jinja2")
        workflow_content = template.render(
            project_id=project_id,
            region=region,
            service_name=service_name,
            service_account_email=service_account_email,
            workload_identity_provider=workload_identity_provider,
        )

        # Write workflow file
        workflows_dir = os.path.join(work_dir, ".github", "workflows")
        os.makedirs(workflows_dir, exist_ok=True)
        workflow_file = os.path.join(workflows_dir, "deploy.yml")
        with open(workflow_file, "w") as f:
            f.write(workflow_content)

        # Git add, commit, push
        add_result = await run_command(
            "git", "add", ".github/workflows/deploy.yml",
            cwd=work_dir,
        )
        if not add_result.success:
            return (
                f"[YELLOW ACTION] Failed to stage workflow file.\n"
                f"stderr: {add_result.stderr}"
            )

        commit_result = await run_command(
            "git", "commit", "-m", "ci: add Cloud Run deploy workflow with WIF auth",
            cwd=work_dir,
        )
        if not commit_result.success:
            if "nothing to commit" in commit_result.stdout:
                return (
                    "[YELLOW ACTION] Workflow file already exists and is unchanged.\n"
                    f"File: {workflow_file}"
                )
            return (
                f"[YELLOW ACTION] Failed to commit workflow.\n"
                f"stderr: {commit_result.stderr}"
            )

        push_result = await run_command(
            "git", "push",
            cwd=work_dir,
        )
        if not push_result.success:
            return (
                f"[YELLOW ACTION] Workflow committed locally but push failed.\n"
                f"stderr: {push_result.stderr}\n"
                f"File: {workflow_file}"
            )

        return (
            f"[YELLOW ACTION] CI/CD workflow deployed successfully.\n"
            f"Repository: {repo}\n"
            f"Project: {project_id}\n"
            f"Service: {service_name}\n"
            f"Region: {region}\n"
            f"WIF Provider: {workload_identity_provider}\n"
            f"SA: {service_account_email}\n"
            f"Workflow: {workflow_file}\n\n"
            f"Push to main will now auto-deploy to Cloud Run."
        )
