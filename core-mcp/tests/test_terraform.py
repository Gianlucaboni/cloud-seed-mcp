"""Tests for the Terraform tool wrappers."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch, call

import pytest

from core_mcp.tools._subprocess import RunResult

# We import the inner tool functions by registering them on a mock FastMCP and
# then calling the async functions directly.  However, the simplest approach is
# to call the module-level helpers through the register pattern.  Instead,
# we'll test the actual async functions directly by importing the module and
# invoking its registered closures.  To keep things clean we'll just re-define
# small wrappers that mirror the tool logic, or better yet, import the module
# and call the inner functions.

# The tool functions are closures inside register(), so the easiest approach
# for testing is to mock run_command at the module level and call the functions
# via a real FastMCP instance.

from mcp.server.fastmcp import FastMCP
from core_mcp.tools import terraform


@pytest.fixture
def mcp_server():
    """Create a real FastMCP and register Terraform tools."""
    server = FastMCP("test")
    terraform.register(server)
    return server


# ---------------------------------------------------------------------------
# Helper to call a registered tool function by name
# ---------------------------------------------------------------------------

def _get_tool_fn(mcp_server: FastMCP, name: str):
    """Retrieve the underlying async function for a registered tool."""
    tool = mcp_server._tool_manager._tools.get(name)
    assert tool is not None, f"Tool '{name}' not registered"
    return tool.fn


# ---------------------------------------------------------------------------
# terraform_plan
# ---------------------------------------------------------------------------

class TestTerraformPlan:
    @pytest.mark.asyncio
    async def test_success(self, mcp_server, make_run_result):
        plan_json = {
            "format_version": "1.0",
            "resource_changes": [
                {"change": {"actions": ["create"]}},
                {"change": {"actions": ["create"]}},
                {"change": {"actions": ["update"]}},
            ],
        }
        init_ok = make_run_result(0, "Initialized", "")
        plan_ok = make_run_result(0, "Plan: 2 to add, 1 to change", "")
        show_ok = make_run_result(0, json.dumps(plan_json), "")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [init_ok, plan_ok, show_ok]

            fn = _get_tool_fn(mcp_server, "terraform_plan")
            result = await fn("my-project", "/tmp/tf")

        assert "my-project" in result
        assert "create: 2" in result
        assert "update: 1" in result

    @pytest.mark.asyncio
    async def test_relative_path_rejected(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "terraform_plan")
        result = await fn("proj", "relative/path")
        assert "absolute path" in result.lower()

    @pytest.mark.asyncio
    async def test_init_failure(self, mcp_server, make_run_result):
        init_fail = make_run_result(1, "", "init error")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = init_fail

            fn = _get_tool_fn(mcp_server, "terraform_plan")
            result = await fn("proj", "/tmp/tf")

        assert "init failed" in result.lower()
        assert "init error" in result

    @pytest.mark.asyncio
    async def test_plan_failure(self, mcp_server, make_run_result):
        init_ok = make_run_result(0, "", "")
        plan_fail = make_run_result(1, "", "plan error details")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [init_ok, plan_fail]

            fn = _get_tool_fn(mcp_server, "terraform_plan")
            result = await fn("proj", "/tmp/tf")

        assert "plan failed" in result.lower()

    @pytest.mark.asyncio
    async def test_show_json_parse_error(self, mcp_server, make_run_result):
        init_ok = make_run_result(0, "", "")
        plan_ok = make_run_result(0, "", "")
        show_bad_json = make_run_result(0, "NOT JSON", "")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [init_ok, plan_ok, show_bad_json]

            fn = _get_tool_fn(mcp_server, "terraform_plan")
            result = await fn("proj", "/tmp/tf")

        assert "json parsing failed" in result.lower()

    @pytest.mark.asyncio
    async def test_command_not_found(self, mcp_server, make_run_result):
        not_found = make_run_result(-1, "", "Command not found: terraform")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = not_found

            fn = _get_tool_fn(mcp_server, "terraform_plan")
            result = await fn("proj", "/tmp/tf")

        assert "failed" in result.lower() or "not found" in result.lower()


# ---------------------------------------------------------------------------
# terraform_apply
# ---------------------------------------------------------------------------

class TestTerraformApply:
    @pytest.mark.asyncio
    async def test_success(self, mcp_server, make_run_result, tmp_path):
        # Create a fake plan file
        plan_file = tmp_path / "plan.tfplan"
        plan_file.write_text("fake plan")

        show_ok = make_run_result(0, "will create 2 resources", "")
        apply_ok = make_run_result(0, "Apply complete! Resources: 2 added", "")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [show_ok, apply_ok]

            fn = _get_tool_fn(mcp_server, "terraform_apply")
            result = await fn("proj", str(tmp_path))

        assert "YELLOW ACTION" in result
        assert "apply completed" in result.lower() or "Apply complete" in result

    @pytest.mark.asyncio
    async def test_no_plan_file(self, mcp_server, tmp_path):
        fn = _get_tool_fn(mcp_server, "terraform_apply")
        result = await fn("proj", str(tmp_path))
        assert "run terraform_plan first" in result.lower()

    @pytest.mark.asyncio
    async def test_relative_path_rejected(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "terraform_apply")
        result = await fn("proj", "relative")
        assert "absolute path" in result.lower()

    @pytest.mark.asyncio
    async def test_apply_failure(self, mcp_server, make_run_result, tmp_path):
        plan_file = tmp_path / "plan.tfplan"
        plan_file.write_text("fake")

        show_ok = make_run_result(0, "preview", "")
        apply_fail = make_run_result(1, "", "apply error")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [show_ok, apply_fail]

            fn = _get_tool_fn(mcp_server, "terraform_apply")
            result = await fn("proj", str(tmp_path))

        assert "failed" in result.lower()
        assert "YELLOW ACTION" in result


# ---------------------------------------------------------------------------
# terraform_show_state
# ---------------------------------------------------------------------------

class TestTerraformShowState:
    @pytest.mark.asyncio
    async def test_success(self, mcp_server, make_run_result):
        state_output = "google_storage_bucket.main\ngoogle_compute_instance.vm1"
        state_ok = make_run_result(0, state_output, "")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = state_ok

            fn = _get_tool_fn(mcp_server, "terraform_show_state")
            result = await fn("proj", "/tmp/tf")

        assert "2" in result  # 2 resources
        assert "google_storage_bucket.main" in result
        assert "google_compute_instance.vm1" in result

    @pytest.mark.asyncio
    async def test_no_state(self, mcp_server, make_run_result):
        no_state = make_run_result(1, "", "No state file was found")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = no_state

            fn = _get_tool_fn(mcp_server, "terraform_show_state")
            result = await fn("proj", "/tmp/tf")

        assert "no terraform state" in result.lower() or "does not exist" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_module_path(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "terraform_show_state")
        result = await fn("proj", "")
        assert "required" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_state(self, mcp_server, make_run_result):
        empty_state = make_run_result(0, "", "")

        with patch("core_mcp.tools.terraform.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = empty_state

            fn = _get_tool_fn(mcp_server, "terraform_show_state")
            result = await fn("proj", "/tmp/tf")

        assert "empty" in result.lower()
