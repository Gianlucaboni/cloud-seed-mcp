"""Dynamic tool loader — loads promoted tools from the PostgreSQL tool_registry.

Tools are loaded at server startup and then periodically via a background
polling task that picks up newly promoted tools without requiring a restart.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Default polling interval in seconds.
POLL_INTERVAL_SECONDS = 30


async def load_single_tool(source_code: str, name: str, mcp: FastMCP) -> None:
    """Load a single tool from source code and register it with the MCP server.

    The source code must define a ``register(mcp: FastMCP) -> None`` function.
    This function is called with the server instance to register the tool.

    Args:
        source_code: Complete Python source code for the tool module.
        name: Tool name (used for logging).
        mcp: The FastMCP server instance.

    Raises:
        ValueError: If the source code does not define a ``register`` function.
        Exception: Any exception raised during exec or registration.
    """
    namespace: dict = {}
    exec(source_code, namespace)  # noqa: S102 — code has passed scanner.py before promotion

    register_fn = namespace.get("register")
    if register_fn is None:
        raise ValueError(f"Tool '{name}' source code does not define a register() function")
    if not callable(register_fn):
        raise ValueError(f"Tool '{name}' register is not callable")

    register_fn(mcp)
    logger.info("Loaded dynamic tool: %s", name)


async def load_tools_from_registry(
    pool: asyncpg.Pool,
    mcp: FastMCP,
    *,
    loaded_tools: set[str] | None = None,
) -> int:
    """Load active tools from the tool_registry that haven't been loaded yet.

    Tools that fail to load are logged and skipped — one broken tool does
    not prevent the server from starting.

    Args:
        pool: asyncpg connection pool.
        mcp: The FastMCP server instance.
        loaded_tools: Set of already-loaded tool names (mutated in place).
            If *None*, a new empty set is used (first boot).

    Returns:
        Number of **newly** loaded tools in this call.
    """
    if loaded_tools is None:
        loaded_tools = set()

    rows = await pool.fetch(
        "SELECT name, source_code FROM tool_registry "
        "WHERE status = 'active' AND source_code IS NOT NULL"
    )

    loaded = 0
    for row in rows:
        name = row["name"]
        if name in loaded_tools:
            continue
        try:
            await load_single_tool(row["source_code"], name, mcp)
            loaded_tools.add(name)
            loaded += 1
        except Exception:
            logger.exception("Failed to load dynamic tool '%s', skipping", name)

    return loaded


async def poll_registry(
    pool: asyncpg.Pool,
    mcp: FastMCP,
    loaded_tools: set[str],
    interval: float = POLL_INTERVAL_SECONDS,
) -> None:
    """Background task that periodically checks for newly promoted tools.

    Runs until cancelled (typically at server shutdown).
    """
    while True:
        await asyncio.sleep(interval)
        try:
            new = await load_tools_from_registry(pool, mcp, loaded_tools=loaded_tools)
            if new:
                logger.info("Hot-loaded %d new dynamic tool(s)", new)
        except Exception:
            logger.exception("Error polling tool registry")
