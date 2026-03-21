"""Shared fixtures for Core MCP tool tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from core_mcp.tools._subprocess import RunResult


@pytest.fixture
def mock_run_command():
    """Fixture that patches ``run_command`` and returns the mock.

    Usage::

        def test_something(mock_run_command):
            mock_run_command.return_value = RunResult(0, "ok", "")
            # ... call your tool ...
            mock_run_command.assert_called_once()
    """
    with patch("core_mcp.tools._subprocess.run_command", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def make_run_result():
    """Factory fixture to easily build RunResult objects."""

    def _make(
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> RunResult:
        return RunResult(returncode=returncode, stdout=stdout, stderr=stderr)

    return _make


@pytest.fixture
def success_result(make_run_result):
    """A generic successful RunResult."""
    return make_run_result(0, "ok", "")


@pytest.fixture
def failure_result(make_run_result):
    """A generic failed RunResult."""
    return make_run_result(1, "", "something went wrong")


@pytest.fixture
def command_not_found_result(make_run_result):
    """A RunResult representing a missing binary."""
    return make_run_result(-1, "", "Command not found: terraform")
