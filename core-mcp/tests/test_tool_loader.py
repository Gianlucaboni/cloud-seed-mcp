"""Tests for the dynamic tool loader."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp.server.fastmcp import FastMCP

from core_mcp.tool_loader import (
    load_single_tool,
    load_tools_from_registry,
    poll_registry,
)


# ---------------------------------------------------------------------------
# load_single_tool
# ---------------------------------------------------------------------------

class TestLoadSingleTool:
    @pytest.mark.asyncio
    async def test_loads_valid_tool(self):
        """A valid tool source with register() should register on the server."""
        mcp = FastMCP("test")
        source = (
            "from mcp.server.fastmcp import FastMCP\n"
            "\n"
            "def register(mcp: FastMCP) -> None:\n"
            "    @mcp.tool()\n"
            "    async def hello_dynamic() -> str:\n"
            "        \"\"\"Say hello.\"\"\"\n"
            "        return 'Hello from dynamic tool!'\n"
        )
        await load_single_tool(source, "hello_dynamic", mcp)
        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "hello_dynamic" in tool_names

    @pytest.mark.asyncio
    async def test_missing_register_raises(self):
        """Source without register() should raise ValueError."""
        mcp = FastMCP("test")
        source = "x = 1\n"
        with pytest.raises(ValueError, match="does not define a register"):
            await load_single_tool(source, "bad_tool", mcp)

    @pytest.mark.asyncio
    async def test_register_not_callable_raises(self):
        """register that is not callable should raise ValueError."""
        mcp = FastMCP("test")
        source = "register = 42\n"
        with pytest.raises(ValueError, match="not callable"):
            await load_single_tool(source, "bad_tool", mcp)

    @pytest.mark.asyncio
    async def test_syntax_error_raises(self):
        """Source with syntax errors should raise SyntaxError."""
        mcp = FastMCP("test")
        source = "def register(mcp):\n    @@invalid\n"
        with pytest.raises(SyntaxError):
            await load_single_tool(source, "broken", mcp)


# ---------------------------------------------------------------------------
# load_tools_from_registry
# ---------------------------------------------------------------------------

class TestLoadToolsFromRegistry:
    def _make_row(self, name: str, source_code: str) -> dict:
        return {"name": name, "source_code": source_code}

    def _valid_source(self, tool_name: str) -> str:
        return (
            "from mcp.server.fastmcp import FastMCP\n"
            "\n"
            f"def register(mcp: FastMCP) -> None:\n"
            f"    @mcp.tool()\n"
            f"    async def {tool_name}() -> str:\n"
            f"        \"\"\"Dynamic tool.\"\"\"\n"
            f"        return '{tool_name}'\n"
        )

    @pytest.mark.asyncio
    async def test_loads_multiple_tools(self):
        """Should load all active tools from the registry."""
        pool = AsyncMock()
        pool.fetch.return_value = [
            self._make_row("tool_a", self._valid_source("tool_a")),
            self._make_row("tool_b", self._valid_source("tool_b")),
        ]
        mcp = FastMCP("test")
        loaded = await load_tools_from_registry(pool, mcp)
        assert loaded == 2
        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "tool_a" in tool_names
        assert "tool_b" in tool_names

    @pytest.mark.asyncio
    async def test_skips_broken_tool(self):
        """A broken tool should be skipped without crashing."""
        pool = AsyncMock()
        pool.fetch.return_value = [
            self._make_row("good", self._valid_source("good")),
            self._make_row("broken", "raise RuntimeError('boom')"),
            self._make_row("also_good", self._valid_source("also_good")),
        ]
        mcp = FastMCP("test")
        loaded = await load_tools_from_registry(pool, mcp)
        assert loaded == 2  # broken skipped

    @pytest.mark.asyncio
    async def test_empty_registry(self):
        """Empty registry should return 0."""
        pool = AsyncMock()
        pool.fetch.return_value = []
        mcp = FastMCP("test")
        loaded = await load_tools_from_registry(pool, mcp)
        assert loaded == 0

    @pytest.mark.asyncio
    async def test_skips_already_loaded_tools(self):
        """Tools already in loaded_tools set should not be loaded again."""
        pool = AsyncMock()
        pool.fetch.return_value = [
            self._make_row("tool_a", self._valid_source("tool_a")),
            self._make_row("tool_b", self._valid_source("tool_b")),
        ]
        mcp = FastMCP("test")
        already_loaded = {"tool_a"}
        loaded = await load_tools_from_registry(pool, mcp, loaded_tools=already_loaded)
        assert loaded == 1  # only tool_b is new
        assert already_loaded == {"tool_a", "tool_b"}

    @pytest.mark.asyncio
    async def test_loaded_tools_set_updated(self):
        """loaded_tools set should be mutated to include newly loaded tools."""
        pool = AsyncMock()
        pool.fetch.return_value = [
            self._make_row("tool_x", self._valid_source("tool_x")),
        ]
        mcp = FastMCP("test")
        tracker: set[str] = set()
        await load_tools_from_registry(pool, mcp, loaded_tools=tracker)
        assert "tool_x" in tracker


# ---------------------------------------------------------------------------
# poll_registry
# ---------------------------------------------------------------------------

class TestPollRegistry:
    def _valid_source(self, tool_name: str) -> str:
        return (
            "from mcp.server.fastmcp import FastMCP\n"
            "\n"
            f"def register(mcp: FastMCP) -> None:\n"
            f"    @mcp.tool()\n"
            f"    async def {tool_name}() -> str:\n"
            f"        \"\"\"Dynamic tool.\"\"\"\n"
            f"        return '{tool_name}'\n"
        )

    @pytest.mark.asyncio
    async def test_picks_up_new_tool(self):
        """Polling should load a tool that appears after the first call."""
        pool = AsyncMock()
        mcp = FastMCP("test")
        loaded_tools: set[str] = set()

        # First poll: nothing
        pool.fetch.return_value = []
        task = asyncio.create_task(
            poll_registry(pool, mcp, loaded_tools, interval=0.01)
        )
        await asyncio.sleep(0.05)

        # Second poll: new tool appears
        pool.fetch.return_value = [
            {"name": "new_tool", "source_code": self._valid_source("new_tool")},
        ]
        await asyncio.sleep(0.05)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert "new_tool" in loaded_tools
