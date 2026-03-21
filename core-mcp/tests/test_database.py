"""Tests for the Database tool wrappers."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from core_mcp.tools._subprocess import RunResult
from mcp.server.fastmcp import FastMCP
from core_mcp.tools import database


@pytest.fixture
def mcp_server():
    server = FastMCP("test")
    database.register(server)
    return server


def _get_tool_fn(mcp_server: FastMCP, name: str):
    tool = mcp_server._tool_manager._tools.get(name)
    assert tool is not None, f"Tool '{name}' not registered"
    return tool.fn


# ---------------------------------------------------------------------------
# database_create_dataset  (BigQuery)
# ---------------------------------------------------------------------------

class TestDatabaseCreateDataset:
    @pytest.mark.asyncio
    async def test_success(self, mcp_server, make_run_result, tmp_path):
        init_ok = make_run_result(0, "Initialized", "")
        plan_ok = make_run_result(0, "Plan: 1 to add", "")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [init_ok, plan_ok]

            fn = _get_tool_fn(mcp_server, "database_create_dataset")
            result = await fn("my-proj", "analytics", tf_dir=str(tmp_path))

        assert "YELLOW ACTION" in result
        assert "analytics" in result
        assert "plan generated" in result.lower() or "successfully" in result.lower()

        # Verify the HCL file was written
        tf_file = tmp_path / "bigquery_analytics.tf"
        assert tf_file.exists()
        content = tf_file.read_text()
        assert "google_bigquery_dataset" in content
        assert "analytics" in content

    @pytest.mark.asyncio
    async def test_no_tf_dir(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "database_create_dataset")
        result = await fn("proj", "ds")
        assert "required" in result.lower()

    @pytest.mark.asyncio
    async def test_relative_tf_dir(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "database_create_dataset")
        result = await fn("proj", "ds", tf_dir="relative/path")
        assert "absolute path" in result.lower()

    @pytest.mark.asyncio
    async def test_init_failure(self, mcp_server, make_run_result, tmp_path):
        init_fail = make_run_result(1, "", "init error")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = init_fail

            fn = _get_tool_fn(mcp_server, "database_create_dataset")
            result = await fn("proj", "ds", tf_dir=str(tmp_path))

        assert "init failed" in result.lower()

    @pytest.mark.asyncio
    async def test_plan_failure(self, mcp_server, make_run_result, tmp_path):
        init_ok = make_run_result(0, "", "")
        plan_fail = make_run_result(1, "", "plan error")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [init_ok, plan_fail]

            fn = _get_tool_fn(mcp_server, "database_create_dataset")
            result = await fn("proj", "ds", tf_dir=str(tmp_path))

        assert "plan failed" in result.lower()

    @pytest.mark.asyncio
    async def test_custom_location(self, mcp_server, make_run_result, tmp_path):
        init_ok = make_run_result(0, "", "")
        plan_ok = make_run_result(0, "", "")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [init_ok, plan_ok]

            fn = _get_tool_fn(mcp_server, "database_create_dataset")
            result = await fn("proj", "ds", location="US", tf_dir=str(tmp_path))

        assert "US" in result
        # Verify HCL has the correct location
        tf_file = tmp_path / "bigquery_ds.tf"
        content = tf_file.read_text()
        assert 'location   = "US"' in content


# ---------------------------------------------------------------------------
# database_create_instance  (Cloud SQL)
# ---------------------------------------------------------------------------

class TestDatabaseCreateInstance:
    @pytest.mark.asyncio
    async def test_success(self, mcp_server, make_run_result, tmp_path):
        init_ok = make_run_result(0, "", "")
        plan_ok = make_run_result(0, "Plan: 1 to add", "")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [init_ok, plan_ok]

            fn = _get_tool_fn(mcp_server, "database_create_instance")
            result = await fn("proj", "my-db", tf_dir=str(tmp_path))

        assert "YELLOW ACTION" in result
        assert "my-db" in result

        tf_file = tmp_path / "cloudsql_my-db.tf"
        assert tf_file.exists()
        content = tf_file.read_text()
        assert "google_sql_database_instance" in content
        assert "my-db" in content

    @pytest.mark.asyncio
    async def test_unsupported_db_type(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "database_create_instance")
        result = await fn("proj", "inst", db_type="firestore", tf_dir="/tmp/tf")
        assert "unsupported" in result.lower()

    @pytest.mark.asyncio
    async def test_no_tf_dir(self, mcp_server):
        fn = _get_tool_fn(mcp_server, "database_create_instance")
        result = await fn("proj", "inst")
        assert "required" in result.lower()

    @pytest.mark.asyncio
    async def test_init_failure(self, mcp_server, make_run_result, tmp_path):
        init_fail = make_run_result(1, "", "init failed")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.return_value = init_fail

            fn = _get_tool_fn(mcp_server, "database_create_instance")
            result = await fn("proj", "inst", tf_dir=str(tmp_path))

        assert "init failed" in result.lower()


# ---------------------------------------------------------------------------
# database_list_databases
# ---------------------------------------------------------------------------

class TestDatabaseListDatabases:
    @pytest.mark.asyncio
    async def test_success_both(self, mcp_server, make_run_result):
        bq_json = json.dumps([
            {"datasetReference": {"datasetId": "analytics"}, "location": "EU"},
        ])
        sql_json = json.dumps([
            {
                "name": "prod-db",
                "databaseVersion": "POSTGRES_15",
                "state": "RUNNABLE",
                "region": "europe-west1",
            },
        ])
        bq_ok = make_run_result(0, bq_json, "")
        sql_ok = make_run_result(0, sql_json, "")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [bq_ok, sql_ok]

            fn = _get_tool_fn(mcp_server, "database_list_databases")
            result = await fn("my-proj")

        assert "analytics" in result
        assert "prod-db" in result
        assert "POSTGRES_15" in result

    @pytest.mark.asyncio
    async def test_empty_results(self, mcp_server, make_run_result):
        bq_ok = make_run_result(0, "[]", "")
        sql_ok = make_run_result(0, "[]", "")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [bq_ok, sql_ok]

            fn = _get_tool_fn(mcp_server, "database_list_databases")
            result = await fn("proj")

        assert "none" in result.lower()

    @pytest.mark.asyncio
    async def test_bq_failure_with_fallback(self, mcp_server, make_run_result):
        bq_fail = make_run_result(1, "", "command failed")
        bq_alt_ok = make_run_result(0, "[]", "")
        sql_ok = make_run_result(0, "[]", "")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [bq_fail, bq_alt_ok, sql_ok]

            fn = _get_tool_fn(mcp_server, "database_list_databases")
            result = await fn("proj")

        # Should still produce output without crashing
        assert "proj" in result

    @pytest.mark.asyncio
    async def test_all_failures(self, mcp_server, make_run_result):
        bq_fail = make_run_result(1, "", "bq error")
        bq_alt_fail = make_run_result(1, "", "bq alt error")
        sql_fail = make_run_result(1, "", "sql error")

        with patch("core_mcp.tools.database.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [bq_fail, bq_alt_fail, sql_fail]

            fn = _get_tool_fn(mcp_server, "database_list_databases")
            result = await fn("proj")

        assert "unable" in result.lower()
