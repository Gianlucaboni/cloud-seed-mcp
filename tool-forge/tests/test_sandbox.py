"""Tests for tool_forge.sandbox."""

from __future__ import annotations

import pytest

from tool_forge.sandbox import SandboxResult, run_in_sandbox


class TestSandboxResult:
    """Verify the SandboxResult data class."""

    def test_success_when_zero(self) -> None:
        r = SandboxResult(returncode=0, stdout="ok", stderr="")
        assert r.success is True

    def test_failure_when_nonzero(self) -> None:
        r = SandboxResult(returncode=1, stdout="", stderr="error")
        assert r.success is False


class TestRunInSandbox:
    """Integration-style tests that execute real Python subprocesses."""

    async def test_simple_print(self) -> None:
        result = await run_in_sandbox("print('hello sandbox')")
        assert result.success
        assert "hello sandbox" in result.stdout

    async def test_syntax_error_fails(self) -> None:
        result = await run_in_sandbox("def (broken")
        assert not result.success
        assert result.stderr  # Should contain SyntaxError info

    async def test_timeout_kills_process(self) -> None:
        result = await run_in_sandbox(
            "import time; time.sleep(999)",
            timeout=1.0,
        )
        assert not result.success
        assert "timed out" in result.stderr

    async def test_nonzero_exit_code(self) -> None:
        result = await run_in_sandbox("import sys; sys.exit(42)")
        assert not result.success
        assert result.returncode == 42

    async def test_stderr_captured(self) -> None:
        result = await run_in_sandbox("import sys; print('err', file=sys.stderr)")
        assert "err" in result.stderr

    async def test_empty_source_succeeds(self) -> None:
        result = await run_in_sandbox("")
        assert result.success

    async def test_environment_is_restricted(self) -> None:
        # SECRET_KEY should not be in the sandbox environment
        source = "import os; print(os.environ.get('SECRET_KEY', 'not_found'))"
        result = await run_in_sandbox(source)
        assert result.success
        assert "not_found" in result.stdout
