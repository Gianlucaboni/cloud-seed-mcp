"""Tests for the project lifecycle tools."""

from __future__ import annotations

import json
import os
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
# _build_wif_pool_name
# ---------------------------------------------------------------------------

class TestBuildWifPoolName:
    def test_constructs_from_project_number(self):
        result = project._build_wif_pool_name("123456789")
        assert result == "projects/123456789/locations/global/workloadIdentityPools/cloudseed-github-pool"

    def test_uses_constant_pool_id(self):
        result = project._build_wif_pool_name("999")
        assert "cloudseed-github-pool" in result


# ---------------------------------------------------------------------------
# _read_client_projects / _write_projects_tfvars
# ---------------------------------------------------------------------------

class TestTfvarsRoundTrip:
    def test_write_and_read(self, tmp_path):
        tfvars_path = str(tmp_path / "projects.auto.tfvars.json")
        projects = {
            "solar-fox": {
                "project_id": "solar-fox-lab-2026",
                "github_access": [
                    {"type": "owner", "value": "Gianlucaboni"},
                    {"type": "repo", "value": "acme/solar-fox"},
                ],
            }
        }

        project._write_projects_tfvars(
            tfvars_path,
            seed_project_id="pa-cloud-seed",
            org_id="95628101394",
            wif_pool_name="projects/123/locations/global/workloadIdentityPools/cloudseed-github-pool",
            client_projects=projects,
        )

        # Verify JSON structure
        data = json.loads(open(tfvars_path).read())
        assert data["seed_project_id"] == "pa-cloud-seed"
        assert data["org_id"] == "95628101394"
        assert data["wif_pool_name"] == "projects/123/locations/global/workloadIdentityPools/cloudseed-github-pool"
        assert "solar-fox" in data["client_projects"]
        assert len(data["client_projects"]["solar-fox"]["github_access"]) == 2

        # Read back via helper
        parsed = project._read_client_projects(tfvars_path)
        assert "solar-fox" in parsed
        assert parsed["solar-fox"]["project_id"] == "solar-fox-lab-2026"
        assert parsed["solar-fox"]["github_access"][0]["type"] == "owner"
        assert parsed["solar-fox"]["github_access"][0]["value"] == "Gianlucaboni"

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

        call_log = []

        async def mock_run(*args, cwd=None, timeout=None):
            call_log.append((args, cwd))
            # billing list
            if "billing" in args and "list" in args:
                return billing_result
            return ok

        settings_patch = {
            "seed_project_id": "pa-cloud-seed",
            "seed_project_number": "123456789",
            "org_id": "95628101394",
            "github_owner": "Gianlucaboni",
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
        content = json.loads(tfvars.read_text())
        assert "test-proj-2026" in content["client_projects"]
        assert content["wif_pool_name"] == "projects/123456789/locations/global/workloadIdentityPools/cloudseed-github-pool"

        # Verify github_access has the default owner
        proj_data = content["client_projects"]["test-proj-2026"]
        assert proj_data["github_access"] == [{"type": "owner", "value": "Gianlucaboni"}]

        # No bootstrap.auto.tfvars should exist in the main bootstrap dir
        assert not (bootstrap_dir / "bootstrap.auto.tfvars").exists()

        # terraform init and apply should run in projects_dir
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
            "seed_project_number": "",
            "org_id": "",
            "github_owner": "",
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

    @pytest.mark.asyncio
    async def test_create_without_github_owner(self, mcp_server, tmp_path):
        """When no github_owner is set, github_access should be empty."""
        projects_dir = tmp_path / "bootstrap" / "projects"
        projects_dir.mkdir(parents=True)

        ok = RunResult(0, "ok", "")
        billing_result = RunResult(0, "BILLING-123", "")

        async def mock_run(*args, cwd=None, timeout=None):
            if "billing" in args and "list" in args:
                return billing_result
            return ok

        settings_patch = {
            "seed_project_id": "my-seed",
            "seed_project_number": "999",
            "org_id": "123",
            "github_owner": "",
            "bootstrap_dir": str(tmp_path / "bootstrap"),
            "bootstrap_projects_dir": str(projects_dir),
        }

        with patch("core_mcp.tools.project.run_command", side_effect=mock_run), \
             patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):

            fn = _get_tool_fn(mcp_server, "project_create")
            await fn(
                project_id="no-wif-proj",
                tf_base_dir=str(tmp_path / "projects"),
            )

        tfvars = projects_dir / "projects.auto.tfvars.json"
        content = json.loads(tfvars.read_text())
        assert content["client_projects"]["no-wif-proj"]["github_access"] == []


# ---------------------------------------------------------------------------
# project_add_wif
# ---------------------------------------------------------------------------

class TestProjectAddWif:
    @pytest.mark.asyncio
    async def test_adds_wif_entry(self, mcp_server, tmp_path):
        """Verify project_add_wif adds a github_access entry and runs terraform."""
        projects_dir = tmp_path / "bootstrap" / "projects"
        projects_dir.mkdir(parents=True)

        # Pre-populate tfvars with existing project (no github_access)
        tfvars_path = projects_dir / "projects.auto.tfvars.json"
        tfvars_path.write_text(json.dumps({
            "seed_project_id": "my-seed",
            "org_id": "123",
            "wif_pool_name": "",
            "client_projects": {
                "my-project": {"project_id": "my-project", "github_access": []},
            },
        }))

        ok = RunResult(0, "ok", "")
        call_log = []

        async def mock_run(*args, cwd=None, timeout=None):
            call_log.append((args, cwd))
            return ok

        settings_patch = {
            "seed_project_id": "my-seed",
            "seed_project_number": "123456",
            "org_id": "123",
            "github_owner": "",
            "bootstrap_dir": str(tmp_path / "bootstrap"),
            "bootstrap_projects_dir": str(projects_dir),
        }

        with patch("core_mcp.tools.project.run_command", side_effect=mock_run), \
             patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):

            fn = _get_tool_fn(mcp_server, "project_add_wif")
            result = await fn(
                project_id="my-project",
                access_type="owner",
                access_value="Gianlucaboni",
            )

        # Verify tfvars updated with github_access
        data = json.loads(tfvars_path.read_text())
        access = data["client_projects"]["my-project"]["github_access"]
        assert len(access) == 1
        assert access[0] == {"type": "owner", "value": "Gianlucaboni"}

        # Verify wif_pool_name was constructed from project number
        assert data["wif_pool_name"] == "projects/123456/locations/global/workloadIdentityPools/cloudseed-github-pool"

        # Verify output
        assert "WIF access added" in result
        assert "Gianlucaboni" in result

    @pytest.mark.asyncio
    async def test_adds_multiple_entries(self, mcp_server, tmp_path):
        """Can add multiple WIF entries to the same project."""
        projects_dir = tmp_path / "bootstrap" / "projects"
        projects_dir.mkdir(parents=True)

        tfvars_path = projects_dir / "projects.auto.tfvars.json"
        tfvars_path.write_text(json.dumps({
            "seed_project_id": "my-seed",
            "org_id": "123",
            "wif_pool_name": "",
            "client_projects": {
                "my-project": {
                    "project_id": "my-project",
                    "github_access": [{"type": "owner", "value": "Gianlucaboni"}],
                },
            },
        }))

        ok = RunResult(0, "ok", "")

        async def mock_run(*args, cwd=None, timeout=None):
            return ok

        settings_patch = {
            "seed_project_id": "my-seed",
            "seed_project_number": "123456",
            "org_id": "123",
            "github_owner": "",
            "bootstrap_dir": str(tmp_path / "bootstrap"),
            "bootstrap_projects_dir": str(projects_dir),
        }

        with patch("core_mcp.tools.project.run_command", side_effect=mock_run), \
             patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):

            fn = _get_tool_fn(mcp_server, "project_add_wif")
            result = await fn(
                project_id="my-project",
                access_type="repo",
                access_value="AltroUser/specific-repo",
            )

        data = json.loads(tfvars_path.read_text())
        access = data["client_projects"]["my-project"]["github_access"]
        assert len(access) == 2
        assert access[0] == {"type": "owner", "value": "Gianlucaboni"}
        assert access[1] == {"type": "repo", "value": "AltroUser/specific-repo"}
        assert "2 entries" in result

    @pytest.mark.asyncio
    async def test_rejects_duplicate(self, mcp_server, tmp_path):
        """Duplicate entries are rejected without running terraform."""
        projects_dir = tmp_path / "bootstrap" / "projects"
        projects_dir.mkdir(parents=True)

        tfvars_path = projects_dir / "projects.auto.tfvars.json"
        tfvars_path.write_text(json.dumps({
            "seed_project_id": "my-seed",
            "org_id": "123",
            "wif_pool_name": "",
            "client_projects": {
                "my-project": {
                    "project_id": "my-project",
                    "github_access": [{"type": "owner", "value": "Gianlucaboni"}],
                },
            },
        }))

        settings_patch = {
            "seed_project_id": "my-seed",
            "seed_project_number": "123456",
            "org_id": "123",
            "github_owner": "",
            "bootstrap_dir": str(tmp_path / "bootstrap"),
            "bootstrap_projects_dir": str(projects_dir),
        }

        with patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):
            fn = _get_tool_fn(mcp_server, "project_add_wif")
            result = await fn(
                project_id="my-project",
                access_type="owner",
                access_value="Gianlucaboni",
            )

        assert "already exists" in result

    @pytest.mark.asyncio
    async def test_fails_without_project_number(self, mcp_server):
        """Returns error when seed_project_number is not set."""
        settings_patch = {
            "seed_project_id": "my-seed",
            "seed_project_number": "",
            "org_id": "123",
            "github_owner": "",
            "bootstrap_dir": "/tmp",
            "bootstrap_projects_dir": "/tmp/projects",
        }

        with patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):
            fn = _get_tool_fn(mcp_server, "project_add_wif")
            result = await fn(
                project_id="x",
                access_type="owner",
                access_value="someone",
            )

        assert "Error" in result
        assert "CORE_MCP_SEED_PROJECT_NUMBER" in result

    @pytest.mark.asyncio
    async def test_rejects_invalid_type(self, mcp_server):
        """Returns error for invalid access_type."""
        settings_patch = {
            "seed_project_id": "my-seed",
            "seed_project_number": "123",
            "org_id": "123",
            "github_owner": "",
            "bootstrap_dir": "/tmp",
            "bootstrap_projects_dir": "/tmp/projects",
        }

        with patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):
            fn = _get_tool_fn(mcp_server, "project_add_wif")
            result = await fn(
                project_id="x",
                access_type="invalid",
                access_value="someone",
            )

        assert "Error" in result
        assert "'owner' or 'repo'" in result


# ---------------------------------------------------------------------------
# project_remove_wif
# ---------------------------------------------------------------------------

class TestProjectRemoveWif:
    @pytest.mark.asyncio
    async def test_removes_wif_entry(self, mcp_server, tmp_path):
        """Verify project_remove_wif removes a github_access entry."""
        projects_dir = tmp_path / "bootstrap" / "projects"
        projects_dir.mkdir(parents=True)

        tfvars_path = projects_dir / "projects.auto.tfvars.json"
        tfvars_path.write_text(json.dumps({
            "seed_project_id": "my-seed",
            "org_id": "123",
            "wif_pool_name": "",
            "client_projects": {
                "my-project": {
                    "project_id": "my-project",
                    "github_access": [
                        {"type": "owner", "value": "Gianlucaboni"},
                        {"type": "repo", "value": "AltroUser/repo"},
                    ],
                },
            },
        }))

        ok = RunResult(0, "ok", "")

        async def mock_run(*args, cwd=None, timeout=None):
            return ok

        settings_patch = {
            "seed_project_id": "my-seed",
            "seed_project_number": "123456",
            "org_id": "123",
            "github_owner": "",
            "bootstrap_dir": str(tmp_path / "bootstrap"),
            "bootstrap_projects_dir": str(projects_dir),
        }

        with patch("core_mcp.tools.project.run_command", side_effect=mock_run), \
             patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):

            fn = _get_tool_fn(mcp_server, "project_remove_wif")
            result = await fn(
                project_id="my-project",
                access_type="repo",
                access_value="AltroUser/repo",
            )

        data = json.loads(tfvars_path.read_text())
        access = data["client_projects"]["my-project"]["github_access"]
        assert len(access) == 1
        assert access[0] == {"type": "owner", "value": "Gianlucaboni"}
        assert "WIF access removed" in result
        assert "Remaining WIF access (1 entries)" in result

    @pytest.mark.asyncio
    async def test_remove_last_entry(self, mcp_server, tmp_path):
        """Removing the last entry warns about no remaining access."""
        projects_dir = tmp_path / "bootstrap" / "projects"
        projects_dir.mkdir(parents=True)

        tfvars_path = projects_dir / "projects.auto.tfvars.json"
        tfvars_path.write_text(json.dumps({
            "seed_project_id": "my-seed",
            "org_id": "123",
            "wif_pool_name": "",
            "client_projects": {
                "my-project": {
                    "project_id": "my-project",
                    "github_access": [{"type": "owner", "value": "Gianlucaboni"}],
                },
            },
        }))

        ok = RunResult(0, "ok", "")

        async def mock_run(*args, cwd=None, timeout=None):
            return ok

        settings_patch = {
            "seed_project_id": "my-seed",
            "seed_project_number": "123456",
            "org_id": "123",
            "github_owner": "",
            "bootstrap_dir": str(tmp_path / "bootstrap"),
            "bootstrap_projects_dir": str(projects_dir),
        }

        with patch("core_mcp.tools.project.run_command", side_effect=mock_run), \
             patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):

            fn = _get_tool_fn(mcp_server, "project_remove_wif")
            result = await fn(
                project_id="my-project",
                access_type="owner",
                access_value="Gianlucaboni",
            )

        assert "No WIF access remains" in result

    @pytest.mark.asyncio
    async def test_remove_nonexistent_entry(self, mcp_server, tmp_path):
        """Removing an entry that doesn't exist is a no-op."""
        projects_dir = tmp_path / "bootstrap" / "projects"
        projects_dir.mkdir(parents=True)

        tfvars_path = projects_dir / "projects.auto.tfvars.json"
        tfvars_path.write_text(json.dumps({
            "seed_project_id": "my-seed",
            "org_id": "123",
            "wif_pool_name": "",
            "client_projects": {
                "my-project": {
                    "project_id": "my-project",
                    "github_access": [{"type": "owner", "value": "Gianlucaboni"}],
                },
            },
        }))

        settings_patch = {
            "seed_project_id": "my-seed",
            "seed_project_number": "123456",
            "org_id": "123",
            "github_owner": "",
            "bootstrap_dir": str(tmp_path / "bootstrap"),
            "bootstrap_projects_dir": str(projects_dir),
        }

        with patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):
            fn = _get_tool_fn(mcp_server, "project_remove_wif")
            result = await fn(
                project_id="my-project",
                access_type="repo",
                access_value="nonexistent/repo",
            )

        assert "not found" in result
        assert "No changes made" in result


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
            "seed_project_number": "999",
            "github_owner": "",
            "bootstrap_dir": "/tmp",
            "bootstrap_projects_dir": "/tmp/projects",
        }

        with patch("core_mcp.tools.project.run_command", new_callable=AsyncMock, return_value=ok), \
             patch("core_mcp.tools.project.Settings", return_value=type("S", (), settings_patch)()):

            fn = _get_tool_fn(mcp_server, "project_list")
            result = await fn()

        assert "proj-a" in result
        assert "Project A" in result
