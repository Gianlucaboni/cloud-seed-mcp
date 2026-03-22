"""Tests for the GitHub tool wrappers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core_mcp.tools._subprocess import RunResult
from mcp.server.fastmcp import FastMCP
from core_mcp.tools import github


@pytest.fixture
def mcp_server():
    server = FastMCP("test")
    github.register(server)
    return server


def _get_tool_fn(mcp_server: FastMCP, name: str):
    tool = mcp_server._tool_manager._tools.get(name)
    assert tool is not None, f"Tool '{name}' not registered"
    return tool.fn


# ---------------------------------------------------------------------------
# github_create_repo
# ---------------------------------------------------------------------------

class TestGithubCreateRepo:
    @pytest.mark.asyncio
    async def test_success_private(self, mcp_server, make_run_result):
        ok = make_run_result(0, "https://github.com/org/my-repo", "")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "github_create_repo")
            result = await fn("my-repo", description="Test repo", private=True)

        assert "YELLOW ACTION" in result
        assert "my-repo" in result
        assert "private" in result.lower()
        # Verify --private flag was used
        call_args = mock_cmd.call_args[0]
        assert "--private" in call_args

    @pytest.mark.asyncio
    async def test_success_public(self, mcp_server, make_run_result):
        ok = make_run_result(0, "https://github.com/org/my-repo", "")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "github_create_repo")
            result = await fn("my-repo", private=False)

        call_args = mock_cmd.call_args[0]
        assert "--public" in call_args

    @pytest.mark.asyncio
    async def test_failure(self, mcp_server, make_run_result):
        fail = make_run_result(1, "", "authentication required")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = fail

            fn = _get_tool_fn(mcp_server, "github_create_repo")
            result = await fn("my-repo")

        assert "failed" in result.lower()
        assert "authentication required" in result

    @pytest.mark.asyncio
    async def test_with_description(self, mcp_server, make_run_result):
        ok = make_run_result(0, "https://github.com/org/my-repo", "")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "github_create_repo")
            await fn("my-repo", description="My great project")

        call_args = mock_cmd.call_args[0]
        assert "--description" in call_args
        assert "My great project" in call_args


# ---------------------------------------------------------------------------
# github_list_repos
# ---------------------------------------------------------------------------

class TestGithubListRepos:
    @pytest.mark.asyncio
    async def test_success(self, mcp_server, make_run_result):
        repos_json = json.dumps([
            {
                "name": "repo1",
                "description": "First repo",
                "visibility": "private",
                "updatedAt": "2024-01-01T00:00:00Z",
            },
            {
                "name": "repo2",
                "description": None,
                "visibility": "public",
                "updatedAt": "2024-06-15T12:00:00Z",
            },
        ])
        ok = make_run_result(0, repos_json, "")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "github_list_repos")
            result = await fn()

        assert "repo1" in result
        assert "repo2" in result
        assert "2" in result  # count
        assert "(no description)" in result  # for repo2

    @pytest.mark.asyncio
    async def test_empty(self, mcp_server, make_run_result):
        ok = make_run_result(0, "[]", "")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "github_list_repos")
            result = await fn()

        assert "no repositories" in result.lower()

    @pytest.mark.asyncio
    async def test_with_org(self, mcp_server, make_run_result):
        ok = make_run_result(0, "[]", "")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "github_list_repos")
            await fn(org="my-org")

        call_args = mock_cmd.call_args[0]
        assert "my-org" in call_args

    @pytest.mark.asyncio
    async def test_failure(self, mcp_server, make_run_result):
        fail = make_run_result(1, "", "not authenticated")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = fail

            fn = _get_tool_fn(mcp_server, "github_list_repos")
            result = await fn()

        assert "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_bad_json(self, mcp_server, make_run_result):
        ok = make_run_result(0, "NOT JSON", "")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "github_list_repos")
            result = await fn()

        assert "failed to parse" in result.lower()


# ---------------------------------------------------------------------------
# github_push_files
# ---------------------------------------------------------------------------

class TestGithubPushFiles:
    @pytest.mark.asyncio
    async def test_success(self, mcp_server, make_run_result):
        checkout_ok = make_run_result(0, "", "")
        add_ok = make_run_result(0, "", "")
        commit_ok = make_run_result(0, "[main abc1234] my commit", "")
        push_ok = make_run_result(0, "", "To github.com:org/repo.git")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [checkout_ok, add_ok, commit_ok, push_ok]

            fn = _get_tool_fn(mcp_server, "github_push_files")
            result = await fn(
                repo="org/repo",
                branch="main",
                files=["file1.py", "file2.py"],
                message="my commit",
                work_dir="/tmp/clone",
            )

        assert "YELLOW ACTION" in result
        assert "2 file(s)" in result
        assert "org/repo:main" in result

    @pytest.mark.asyncio
    async def test_no_work_dir(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "github_push_files")
        result = await fn(
            repo="org/repo", branch="main",
            files=["f.py"], message="msg", work_dir="",
        )
        assert "required" in result.lower()

    @pytest.mark.asyncio
    async def test_relative_work_dir(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "github_push_files")
        result = await fn(
            repo="org/repo", branch="main",
            files=["f.py"], message="msg", work_dir="relative/path",
        )
        assert "absolute path" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_files_list(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "github_push_files")
        result = await fn(
            repo="org/repo", branch="main",
            files=[], message="msg", work_dir="/tmp/clone",
        )
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_nothing_to_commit(self, mcp_server, make_run_result):
        checkout_ok = make_run_result(0, "", "")
        add_ok = make_run_result(0, "", "")
        commit_nothing = make_run_result(1, "nothing to commit, working tree clean", "")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [checkout_ok, add_ok, commit_nothing]

            fn = _get_tool_fn(mcp_server, "github_push_files")
            result = await fn(
                repo="org/repo", branch="main",
                files=["f.py"], message="msg", work_dir="/tmp/clone",
            )

        assert "no changes" in result.lower() or "up to date" in result.lower()

    @pytest.mark.asyncio
    async def test_push_failure(self, mcp_server, make_run_result):
        checkout_ok = make_run_result(0, "", "")
        add_ok = make_run_result(0, "", "")
        commit_ok = make_run_result(0, "[main abc123] msg", "")
        push_fail = make_run_result(1, "", "permission denied")

        with patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [checkout_ok, add_ok, commit_ok, push_fail]

            fn = _get_tool_fn(mcp_server, "github_push_files")
            result = await fn(
                repo="org/repo", branch="main",
                files=["f.py"], message="msg", work_dir="/tmp/clone",
            )

        assert "push failed" in result.lower()


# ---------------------------------------------------------------------------
# github_setup_cicd
# ---------------------------------------------------------------------------

class TestGithubSetupCicd:
    @pytest.fixture
    def templates_dir(self, tmp_path):
        """Create a temporary templates directory with a minimal deploy template."""
        workflows_dir = tmp_path / "github-workflows"
        workflows_dir.mkdir()
        template = workflows_dir / "deploy.yml.jinja2"
        template.write_text(
            "# Deploy workflow\n"
            "name: Deploy\n"
            "env:\n"
            "  PROJECT_ID: {{ project_id }}\n"
            "  REGION: {{ region }}\n"
            "  SERVICE: {{ service_name }}\n"
            "  SA: {{ service_account_email }}\n"
            "  WIF: {{ workload_identity_provider }}\n"
        )
        return str(tmp_path)

    @pytest.mark.asyncio
    async def test_success(self, mcp_server, make_run_result, tmp_path, templates_dir):
        add_ok = make_run_result(0, "", "")
        commit_ok = make_run_result(0, "", "")
        push_ok = make_run_result(0, "", "")

        work_dir = str(tmp_path / "repo")
        os.makedirs(work_dir)

        with (
            patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd,
            patch("core_mcp.tools.github.Settings") as mock_settings,
        ):
            mock_settings.return_value.templates_dir = templates_dir
            mock_cmd.side_effect = [add_ok, commit_ok, push_ok]
            fn = _get_tool_fn(mcp_server, "github_setup_cicd")
            result = await fn(
                repo="acme/app",
                project_id="acme-prod",
                service_name="acme-api",
                service_account_email="sa-deploy@acme-prod.iam.gserviceaccount.com",
                workload_identity_provider="projects/123/locations/global/workloadIdentityPools/cloudseed-github-pool/providers/cs-acme-github",
                work_dir=work_dir,
            )

        assert "YELLOW ACTION" in result
        assert "successfully" in result
        assert "acme-prod" in result

        # Verify workflow file was written
        wf = Path(work_dir) / ".github" / "workflows" / "deploy.yml"
        assert wf.exists()
        content = wf.read_text()
        assert "acme-prod" in content
        assert "acme-api" in content

    @pytest.mark.asyncio
    async def test_no_work_dir(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "github_setup_cicd")
        result = await fn(
            repo="acme/app", project_id="p", service_name="s",
            service_account_email="sa@x", workload_identity_provider="wif",
        )
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_relative_work_dir(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "github_setup_cicd")
        result = await fn(
            repo="acme/app", project_id="p", service_name="s",
            service_account_email="sa@x", workload_identity_provider="wif",
            work_dir="relative/path",
        )
        assert "Error" in result
        assert "absolute" in result

    @pytest.mark.asyncio
    async def test_push_failure(self, mcp_server, make_run_result, tmp_path, templates_dir):
        add_ok = make_run_result(0, "", "")
        commit_ok = make_run_result(0, "", "")
        push_fail = make_run_result(1, "", "rejected")

        work_dir = str(tmp_path / "repo")
        os.makedirs(work_dir)

        with (
            patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd,
            patch("core_mcp.tools.github.Settings") as mock_settings,
        ):
            mock_settings.return_value.templates_dir = templates_dir
            mock_cmd.side_effect = [add_ok, commit_ok, push_fail]
            fn = _get_tool_fn(mcp_server, "github_setup_cicd")
            result = await fn(
                repo="acme/app", project_id="p", service_name="s",
                service_account_email="sa@x", workload_identity_provider="wif",
                work_dir=work_dir,
            )

        assert "push failed" in result

    @pytest.mark.asyncio
    async def test_template_rendering(self, mcp_server, make_run_result, tmp_path, templates_dir):
        """Verify the rendered workflow contains all expected values."""
        add_ok = make_run_result(0, "", "")
        commit_ok = make_run_result(0, "", "")
        push_ok = make_run_result(0, "", "")

        work_dir = str(tmp_path / "repo")
        os.makedirs(work_dir)

        with (
            patch("core_mcp.tools.github.run_command", new_callable=AsyncMock) as mock_cmd,
            patch("core_mcp.tools.github.Settings") as mock_settings,
        ):
            mock_settings.return_value.templates_dir = templates_dir
            mock_cmd.side_effect = [add_ok, commit_ok, push_ok]
            fn = _get_tool_fn(mcp_server, "github_setup_cicd")
            await fn(
                repo="acme/app",
                project_id="my-project",
                service_name="my-service",
                service_account_email="deploy@my-project.iam",
                workload_identity_provider="projects/999/locations/global/pools/pool/providers/prov",
                region="us-central1",
                work_dir=work_dir,
            )

        wf = Path(work_dir) / ".github" / "workflows" / "deploy.yml"
        content = wf.read_text()
        assert "my-project" in content
        assert "us-central1" in content
        assert "my-service" in content
        assert "deploy@my-project.iam" in content
        assert "projects/999" in content
