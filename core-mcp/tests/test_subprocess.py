"""Tests for the shared subprocess helper."""

from __future__ import annotations

import pytest

from core_mcp.tools._subprocess import RunResult, run_command


class TestRunResult:
    def test_success_property(self):
        r = RunResult(returncode=0, stdout="ok", stderr="")
        assert r.success is True

    def test_failure_property(self):
        r = RunResult(returncode=1, stdout="", stderr="err")
        assert r.success is False

    def test_frozen(self):
        r = RunResult(returncode=0, stdout="", stderr="")
        with pytest.raises(AttributeError):
            r.returncode = 1  # type: ignore[misc]


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_simple_command(self):
        """Run a real command to verify the plumbing works."""
        result = await run_command("echo", "hello world")
        assert result.success
        assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_command_not_found(self):
        result = await run_command("nonexistent_binary_xyz_123")
        assert not result.success
        assert result.returncode == -1
        assert "command not found" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_nonzero_exit(self):
        result = await run_command("false")
        assert not result.success
        assert result.returncode != 0

    @pytest.mark.asyncio
    async def test_cwd(self, tmp_path):
        result = await run_command("pwd", cwd=str(tmp_path))
        assert result.success
        # On macOS /tmp may resolve to /private/tmp
        assert tmp_path.name in result.stdout

    @pytest.mark.asyncio
    async def test_env(self):
        result = await run_command(
            "env", env={"MY_TEST_VAR_XYZ": "hello123"}
        )
        assert result.success
        assert "MY_TEST_VAR_XYZ=hello123" in result.stdout

    @pytest.mark.asyncio
    async def test_timeout(self):
        result = await run_command("sleep", "10", timeout=0.1)
        assert not result.success
        assert result.returncode == -2
        assert "timed out" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_stderr_captured(self):
        result = await run_command("ls", "/nonexistent_path_xyz_123")
        assert not result.success
        assert result.stderr  # should have error message
