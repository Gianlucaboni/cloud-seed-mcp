"""Tests for tool_forge.registry.

These tests verify the registry logic without requiring a real PostgreSQL
database.  We mock asyncpg.Pool and the records it returns.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tool_forge.registry import (
    ToolRecord,
    ToolStatus,
    compute_code_hash,
    deprecate_tool,
    get_tool,
    list_tools,
    promote_tool,
    register_tool,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(
    name: str = "my_tool",
    status: str = "staging",
    promoted_at: datetime | None = None,
) -> dict:
    """Create a dict mimicking an asyncpg.Record for tool_registry."""
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": name,
        "version": "0.1.0",
        "description": "A test tool",
        "schema_json": json.dumps({"type": "object"}),
        "code_hash": compute_code_hash("print('hello')"),
        "source_code": "def register(mcp): pass",
        "status": status,
        "created_at": datetime.now(timezone.utc),
        "promoted_at": promoted_at,
    }


def _mock_pool() -> AsyncMock:
    """Create a mock asyncpg.Pool."""
    pool = AsyncMock()
    return pool


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeCodeHash:
    def test_deterministic(self) -> None:
        h1 = compute_code_hash("print('hello')")
        h2 = compute_code_hash("print('hello')")
        assert h1 == h2

    def test_different_source_different_hash(self) -> None:
        h1 = compute_code_hash("a = 1")
        h2 = compute_code_hash("a = 2")
        assert h1 != h2

    def test_returns_hex_string(self) -> None:
        h = compute_code_hash("x")
        assert len(h) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in h)


class TestRegisterTool:
    async def test_returns_tool_record(self) -> None:
        pool = _mock_pool()
        row = _make_row(status="staging")
        pool.fetchrow.return_value = row

        record = await register_tool(
            pool,
            name="my_tool",
            version="0.1.0",
            description="A test tool",
            schema_json={"type": "object"},
            source_code="print('hello')",
        )

        assert isinstance(record, ToolRecord)
        assert record.name == "my_tool"
        assert record.status == ToolStatus.STAGING
        pool.fetchrow.assert_awaited_once()


class TestPromoteTool:
    async def test_promote_success(self) -> None:
        pool = _mock_pool()
        now = datetime.now(timezone.utc)
        row = _make_row(status="active", promoted_at=now)
        pool.fetchrow.return_value = row

        record = await promote_tool(
            pool,
            name="my_tool",
            tests_passed=True,
            scan_passed=True,
            sandbox_passed=True,
        )
        assert record.status == ToolStatus.ACTIVE
        assert record.promoted_at is not None

    async def test_promote_fails_when_tests_failed(self) -> None:
        pool = _mock_pool()
        with pytest.raises(ValueError, match="tests"):
            await promote_tool(
                pool,
                name="my_tool",
                tests_passed=False,
                scan_passed=True,
                sandbox_passed=True,
            )

    async def test_promote_fails_when_scan_failed(self) -> None:
        pool = _mock_pool()
        with pytest.raises(ValueError, match="security scan"):
            await promote_tool(
                pool,
                name="my_tool",
                tests_passed=True,
                scan_passed=False,
                sandbox_passed=True,
            )

    async def test_promote_fails_when_sandbox_failed(self) -> None:
        pool = _mock_pool()
        with pytest.raises(ValueError, match="sandbox"):
            await promote_tool(
                pool,
                name="my_tool",
                tests_passed=True,
                scan_passed=True,
                sandbox_passed=False,
            )

    async def test_promote_fails_when_not_found(self) -> None:
        pool = _mock_pool()
        pool.fetchrow.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await promote_tool(
                pool,
                name="nonexistent",
                tests_passed=True,
                scan_passed=True,
                sandbox_passed=True,
            )

    async def test_promote_reports_multiple_failures(self) -> None:
        pool = _mock_pool()
        with pytest.raises(ValueError, match="tests.*security scan.*sandbox"):
            await promote_tool(
                pool,
                name="my_tool",
                tests_passed=False,
                scan_passed=False,
                sandbox_passed=False,
            )


class TestDeprecateTool:
    async def test_deprecate_success(self) -> None:
        pool = _mock_pool()
        row = _make_row(status="deprecated")
        pool.fetchrow.return_value = row

        record = await deprecate_tool(pool, name="my_tool")
        assert record.status == ToolStatus.DEPRECATED

    async def test_deprecate_not_found(self) -> None:
        pool = _mock_pool()
        pool.fetchrow.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await deprecate_tool(pool, name="ghost")


class TestGetTool:
    async def test_found(self) -> None:
        pool = _mock_pool()
        pool.fetchrow.return_value = _make_row()
        record = await get_tool(pool, name="my_tool")
        assert record is not None
        assert record.name == "my_tool"

    async def test_not_found(self) -> None:
        pool = _mock_pool()
        pool.fetchrow.return_value = None
        record = await get_tool(pool, name="nope")
        assert record is None


class TestListTools:
    async def test_list_all(self) -> None:
        pool = _mock_pool()
        pool.fetch.return_value = [_make_row(), _make_row(name="other")]
        records = await list_tools(pool)
        assert len(records) == 2

    async def test_list_with_status_filter(self) -> None:
        pool = _mock_pool()
        pool.fetch.return_value = [_make_row(status="active")]
        records = await list_tools(pool, status=ToolStatus.ACTIVE)
        assert len(records) == 1
        assert records[0].status == ToolStatus.ACTIVE

    async def test_list_empty(self) -> None:
        pool = _mock_pool()
        pool.fetch.return_value = []
        records = await list_tools(pool)
        assert records == []
