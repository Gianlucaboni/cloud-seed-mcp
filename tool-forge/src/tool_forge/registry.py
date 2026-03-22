"""Tool registry — async CRUD operations against the PostgreSQL tool_registry table.

Handles registration (staging), promotion (active), deprecation, listing,
and lookup.  Promotion enforces that tests, scan, and sandbox must have
passed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import asyncpg


class ToolStatus(str, Enum):
    STAGING = "staging"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


@dataclass
class ToolRecord:
    """A row from the tool_registry table."""

    id: str
    name: str
    version: str
    description: str | None
    schema_json: dict[str, Any]
    code_hash: str
    source_code: str | None
    status: ToolStatus
    created_at: datetime
    promoted_at: datetime | None


def compute_code_hash(source: str) -> str:
    """Compute SHA-256 hex digest of tool source code."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _row_to_record(row: asyncpg.Record) -> ToolRecord:
    schema = row["schema_json"]
    if isinstance(schema, str):
        schema = json.loads(schema)
    return ToolRecord(
        id=str(row["id"]),
        name=row["name"],
        version=row["version"],
        description=row["description"],
        schema_json=schema,
        code_hash=row["code_hash"],
        source_code=row["source_code"],
        status=ToolStatus(row["status"]),
        created_at=row["created_at"],
        promoted_at=row["promoted_at"],
    )


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


async def register_tool(
    pool: asyncpg.Pool,
    *,
    name: str,
    version: str,
    description: str,
    schema_json: dict[str, Any],
    source_code: str,
) -> ToolRecord:
    """Insert a new tool in staging status.

    Args:
        pool: asyncpg connection pool.
        name: Unique tool name.
        version: Semantic version string.
        description: Human-readable description.
        schema_json: JSON Schema of the tool's parameters.
        source_code: Full Python source code (used to compute code_hash).

    Returns:
        The created ToolRecord.
    """
    code_hash = compute_code_hash(source_code)
    row = await pool.fetchrow(
        """
        INSERT INTO tool_registry (name, version, description, schema_json, code_hash, source_code, status)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, 'staging')
        RETURNING *
        """,
        name,
        version,
        description,
        json.dumps(schema_json),
        code_hash,
        source_code,
    )
    return _row_to_record(row)


async def promote_tool(
    pool: asyncpg.Pool,
    *,
    name: str,
    tests_passed: bool,
    scan_passed: bool,
    sandbox_passed: bool,
) -> ToolRecord:
    """Promote a staging tool to active status.

    All three quality gates must be True or a ValueError is raised.

    Args:
        pool: asyncpg connection pool.
        name: Tool name to promote.
        tests_passed: Whether the auto-generated tests passed.
        scan_passed: Whether the security scan passed.
        sandbox_passed: Whether the sandbox execution succeeded.

    Returns:
        The updated ToolRecord.

    Raises:
        ValueError: If any quality gate failed or tool not found / not in staging.
    """
    failures: list[str] = []
    if not tests_passed:
        failures.append("tests")
    if not scan_passed:
        failures.append("security scan")
    if not sandbox_passed:
        failures.append("sandbox")
    if failures:
        raise ValueError(
            f"Cannot promote tool '{name}': the following gates failed: "
            + ", ".join(failures)
        )

    row = await pool.fetchrow(
        """
        UPDATE tool_registry
        SET status = 'active', promoted_at = now()
        WHERE name = $1 AND status = 'staging'
        RETURNING *
        """,
        name,
    )
    if row is None:
        raise ValueError(
            f"Tool '{name}' not found in staging status"
        )
    return _row_to_record(row)


async def deprecate_tool(pool: asyncpg.Pool, *, name: str) -> ToolRecord:
    """Mark an active tool as deprecated.

    Args:
        pool: asyncpg connection pool.
        name: Tool name to deprecate.

    Returns:
        The updated ToolRecord.

    Raises:
        ValueError: If tool not found or not in active status.
    """
    row = await pool.fetchrow(
        """
        UPDATE tool_registry
        SET status = 'deprecated'
        WHERE name = $1 AND status = 'active'
        RETURNING *
        """,
        name,
    )
    if row is None:
        raise ValueError(
            f"Tool '{name}' not found in active status"
        )
    return _row_to_record(row)


async def get_tool(pool: asyncpg.Pool, *, name: str) -> ToolRecord | None:
    """Fetch a single tool by name.

    Returns:
        ToolRecord or None if not found.
    """
    row = await pool.fetchrow(
        "SELECT * FROM tool_registry WHERE name = $1",
        name,
    )
    if row is None:
        return None
    return _row_to_record(row)


async def list_tools(
    pool: asyncpg.Pool,
    *,
    status: ToolStatus | None = None,
) -> list[ToolRecord]:
    """List tools, optionally filtered by status.

    Args:
        pool: asyncpg connection pool.
        status: If provided, only return tools with this status.

    Returns:
        List of ToolRecord objects ordered by created_at descending.
    """
    if status is not None:
        rows = await pool.fetch(
            "SELECT * FROM tool_registry WHERE status = $1 ORDER BY created_at DESC",
            status.value,
        )
    else:
        rows = await pool.fetch(
            "SELECT * FROM tool_registry ORDER BY created_at DESC",
        )
    return [_row_to_record(r) for r in rows]
