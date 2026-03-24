"""Tests for the project lifecycle tools."""

from __future__ import annotations

import json
import os
import textwrap
from unittest.mock import AsyncMock, patch

import pytest

from mcp.server.fastmcp import FastMCP
from core_mcp.tools._subprocess import RunResult
from core_mcp.tools import project


@pytest.fixture
def mcp_server():
    """Create a real FastMCP and register project tools."""
    server = FastMCP("test")
    project.register(server)
    return server


def _get_tool_fn(mcp_server: FastMCP, name: str):
    """Retrieve the underlying async function for a registered tool."""
    tool = mcp_server._tool_manager._tools.get(name)
    assert tool is not None, f"Tool '{name}' not registered"
    return tool.fn


# ---------------------------------------------------------------------------
# _read_client_projects / _write_projects_tfvars
# ---------------------------------------------------------------------------

class TestTfvarsRoundTrip:
    def test_write_and_read(self, tmp_path):
        tfvars_path = str(tmp_path / "projects.auto.tfvars.json")
        projects = {
            "solar-fox": {
                "project_id": "solar-fox-lab-2026",
                "github_repo": "acme/solar-fox",
            }
        }

        project._write_projects_tfvars(
            tfvars_path,
            seed_project_id="pa-cloud-seed",
            org_id="95628101394",
            wif_pool_name="projects/123/locations/global/workloadIdentityPools/pool",
            client_projects=projects,
        )

        # Verify JSON structure
        data = json.loads(open(tfvars_path).read())
        assert data["seed_project_id"] == "pa-cloud-seed"
        assert data["org_id"] == "95628101394"
        assert data["wif_pool_name"] == "projects/123/locations/global/workloadIdentityPools/pool"
        assert "solar-fox" in data["client_projects"]

        # Read back via helper
        parsed = project._read_client_projects(tfvars_path)
        assert "solar-fox" in parsed
        assert parsed["solar-fox"]["project_id"] == "solar-fox-lab-2026"
        assert parsed["solar-fox"]["github_repo"] == "acme/solar-fox"

    def test_write_empty_projects(self, tmp_path):
        tfvars_path = str(tmp_path / "projects.auto.tfvars.json")
        project._write_projects_tfvars(
            tfvars_path,
            seed_project_id="my-seed",
            org_id="123",
            wif_pool_name="",
            client_projects={},
        )
        data = json.loads(open(tfvars_path).read())
        assert data["client_projects"] == {}

    def test_read_nonexistent_file(self):
        assert project._read_client_projects("/nonexistent/path") == {}


# ---------------------------------------------------------------------------
# project_create
# ---------------------------------------------------------------------------

class TestProjectCreate:
    @pytest.mark.asyncio
    async def test_uses_projects_dir_not_bootstrap(self, mcp_server, tmp_path):
        """Verify that project_create writes to bootstrap/projects/ and runs
        terraform there, NOT in the main bootstrap directory."""
        projects_dir = tmp_path / "bootstrap" / "projects"
        projects_dir.mkdir(parents=True)
        bootstrap_dir = tmp_path / "bootstrap"

        ok = RunResult(0, "ok", "")
        billing_result = RunResult(0, "010DD5-DAB31A-97E66E", "")
        wif_output = RunResult(
            0,
            "projects/123/locations/global/workloadIdentityPools/cloudseed-github-pool",
            "",
        )

        call_log = []

        async def mock_run(*args, cwd=None, timeout=None):
            call_log.append((args, cwd))
            # billing list
            if "billing" in args and "list" in args:
                return billing_result
            # terraform output for wif
            if "terraform" in args and "output" in args:
                return wif_output
            return ok

        settings_patch = {
            "seed_project_id": "pa-cloud-seed",
            "org_id": "95628101394",
            "bootstrap_dir": str(bootstrap_dir),
            "bootstrap_projects_dir": str(projects_dir),
        }

        with patch("core_mcp.tools.project.run_command", side_effect=mock_run), \
             patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):

            fn = _get_tool_fn(mcp_server, "project_create")
            result = await fn(
                project_id="test-proj-2026",
                tf_base_dir=str(tmp_path / "projects"),
            )

        # The tfvars should be in projects_dir, not bootstrap_dir
        tfvars = projects_dir / "projects.auto.tfvars.json"
        assert tfvars.exists(), "projects.auto.tfvars.json should be in bootstrap/projects/"
        content = tfvars.read_text()
        assert "test-proj-2026" in content
        assert "wif_pool_name" in content

        # No bootstrap.auto.tfvars should exist in the main bootstrap dir
        assert not (bootstrap_dir / "bootstrap.auto.tfvars").exists()

        # terraform init and apply should run in projects_dir
        tf_cwds = [cwd for (args, cwd) in call_log if args and args[0] == "terraform" and cwd is not None]
        # Filter to init/apply calls (not the output call which runs in bootstrap_dir)
        init_apply_cwds = [
            cwd for (args, cwd) in call_log
            if args and args[0] == "terraform" and ("init" in args or "apply" in args)
        ]
        for cwd in init_apply_cwds:
            assert cwd == str(projects_dir), (
                f"terraform init/apply should run in projects dir, got {cwd}"
            )

        assert "SA hierarchy provisioned" in result

    @pytest.mark.asyncio
    async def test_skips_sa_without_env_vars(self, mcp_server, tmp_path):
        """When seed_project_id or org_id are missing, SA provisioning is skipped."""
        ok = RunResult(0, "ok", "")
        billing_result = RunResult(0, "BILLING-123", "")

        async def mock_run(*args, cwd=None, timeout=None):
            if "billing" in args and "list" in args:
                return billing_result
            return ok

        settings_patch = {
            "seed_project_id": "",
            "org_id": "",
            "bootstrap_dir": str(tmp_path),
            "bootstrap_projects_dir": str(tmp_path / "projects"),
        }

        with patch("core_mcp.tools.project.run_command", side_effect=mock_run), \
             patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):

            fn = _get_tool_fn(mcp_server, "project_create")
            result = await fn(
                project_id="no-env-proj",
                tf_base_dir=str(tmp_path / "projects"),
            )

        assert "CORE_MCP_SEED_PROJECT_ID" in result
        assert "Skipping SA hierarchy" in result


# ---------------------------------------------------------------------------
# project_list
# ---------------------------------------------------------------------------

class TestProjectList:
    @pytest.mark.asyncio
    async def test_returns_projects(self, mcp_server):
        projects_json = json.dumps([
            {"projectId": "proj-a", "name": "Project A", "lifecycleState": "ACTIVE"},
        ])
        ok = RunResult(0, projects_json, "")

        settings_patch = {
            "org_id": "123",
            "seed_project_id": "seed",
            "bootstrap_dir": "/tmp",
            "bootstrap_projects_dir": "/tmp/projects",
        }

        with patch("core_mcp.tools.project.run_command", new_callable=AsyncMock, return_value=ok), \
             patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):

            fn = _get_tool_fn(mcp_server, "project_list")
            result = await fn()

        assert "proj-a" in result
        assert "Project A" in result
