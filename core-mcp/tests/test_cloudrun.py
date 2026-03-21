"""Tests for the Cloud Run tool wrappers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from core_mcp.tools._subprocess import RunResult
from mcp.server.fastmcp import FastMCP
from core_mcp.tools import cloudrun


@pytest.fixture
def mcp_server():
    server = FastMCP("test")
    cloudrun.register(server)
    return server


def _get_tool_fn(mcp_server: FastMCP, name: str):
    tool = mcp_server._tool_manager._tools.get(name)
    assert tool is not None, f"Tool '{name}' not registered"
    return tool.fn


# ---------------------------------------------------------------------------
# cloudrun_deploy
# ---------------------------------------------------------------------------

class TestCloudrunDeploy:
    @pytest.mark.asyncio
    async def test_success_json(self, mcp_server, make_run_result):
        deploy_json = json.dumps({
            "status": {
                "url": "https://my-svc-abc123-ew.a.run.app",
                "latestReadyRevisionName": "my-svc-00001-abc",
            },
        })
        ok = make_run_result(0, deploy_json, "")

        with patch("core_mcp.tools.cloudrun.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "cloudrun_deploy")
            result = await fn("my-proj", "my-svc", "gcr.io/my-proj/img:v1")

        assert "YELLOW ACTION" in result
        assert "succeeded" in result.lower()
        assert "my-svc" in result
        assert "https://my-svc-abc123-ew.a.run.app" in result
        assert "my-svc-00001-abc" in result

    @pytest.mark.asyncio
    async def test_success_non_json(self, mcp_server, make_run_result):
        ok = make_run_result(0, "Deploying... done.", "")

        with patch("core_mcp.tools.cloudrun.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "cloudrun_deploy")
            result = await fn("my-proj", "my-svc", "img:v1")

        assert "YELLOW ACTION" in result
        assert "completed" in result.lower()

    @pytest.mark.asyncio
    async def test_failure(self, mcp_server, make_run_result):
        fail = make_run_result(1, "", "permission denied")

        with patch("core_mcp.tools.cloudrun.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = fail

            fn = _get_tool_fn(mcp_server, "cloudrun_deploy")
            result = await fn("proj", "svc", "img:v1")

        assert "YELLOW ACTION" in result
        assert "failed" in result.lower()
        assert "permission denied" in result

    @pytest.mark.asyncio
    async def test_custom_region(self, mcp_server, make_run_result):
        ok = make_run_result(0, "{}", "")

        with patch("core_mcp.tools.cloudrun.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "cloudrun_deploy")
            await fn("proj", "svc", "img:v1", region="us-central1")

        call_args = mock_cmd.call_args[0]
        assert "--region=us-central1" in call_args

    @pytest.mark.asyncio
    async def test_default_flags(self, mcp_server, make_run_result):
        ok = make_run_result(0, "{}", "")

        with patch("core_mcp.tools.cloudrun.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "cloudrun_deploy")
            await fn("proj", "svc", "img:v1")

        call_args = mock_cmd.call_args[0]
        assert "--no-allow-unauthenticated" in call_args
        assert "--platform=managed" in call_args


# ---------------------------------------------------------------------------
# cloudrun_list_services
# ---------------------------------------------------------------------------

class TestCloudrunListServices:
    @pytest.mark.asyncio
    async def test_success(self, mcp_server, make_run_result):
        services_json = json.dumps([
            {
                "metadata": {"name": "svc-1"},
                "status": {
                    "url": "https://svc-1.run.app",
                    "conditions": [{"type": "Ready", "status": "True"}],
                },
            },
            {
                "metadata": {"name": "svc-2"},
                "status": {
                    "url": "https://svc-2.run.app",
                    "conditions": [{"type": "Ready", "status": "False"}],
                },
            },
        ])
        ok = make_run_result(0, services_json, "")

        with patch("core_mcp.tools.cloudrun.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "cloudrun_list_services")
            result = await fn("my-proj")

        assert "svc-1" in result
        assert "svc-2" in result
        assert "Total: 2" in result

    @pytest.mark.asyncio
    async def test_empty(self, mcp_server, make_run_result):
        ok = make_run_result(0, "[]", "")

        with patch("core_mcp.tools.cloudrun.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "cloudrun_list_services")
            result = await fn("proj")

        assert "no cloud run services" in result.lower()

    @pytest.mark.asyncio
    async def test_failure(self, mcp_server, make_run_result):
        fail = make_run_result(1, "", "project not found")

        with patch("core_mcp.tools.cloudrun.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = fail

            fn = _get_tool_fn(mcp_server, "cloudrun_list_services")
            result = await fn("proj")

        assert "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_bad_json(self, mcp_server, make_run_result):
        ok = make_run_result(0, "NOT JSON", "")

        with patch("core_mcp.tools.cloudrun.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = ok

            fn = _get_tool_fn(mcp_server, "cloudrun_list_services")
            result = await fn("proj")

        assert "failed to parse" in result.lower()
