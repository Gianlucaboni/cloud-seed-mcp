"""Shared async subprocess helper for CLI tool wrappers."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RunResult:
    """Result of a subprocess execution."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


async def run_command(
    *args: str,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 300.0,
) -> RunResult:
    """Run a CLI command via asyncio.create_subprocess_exec.

    Args:
        *args: Command and arguments (e.g. "terraform", "plan", "-out=plan.tfplan").
        cwd: Working directory for the command.
        timeout: Maximum seconds to wait before killing the process.
        env: Optional environment variables (merged with os.environ).

    Returns:
        RunResult with returncode, stdout, and stderr.

    Raises:
        FileNotFoundError: If the command binary is not found on PATH.
        asyncio.TimeoutError: If the command exceeds the timeout.
    """
    merged_env: dict[str, str] | None = None
    if env is not None:
        merged_env = {**os.environ, **env}

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=merged_env,
        )
    except FileNotFoundError:
        return RunResult(
            returncode=-1,
            stdout="",
            stderr=f"Command not found: {args[0]}",
        )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()  # drain pipes
        return RunResult(
            returncode=-2,
            stdout="",
            stderr=f"Command timed out after {timeout}s: {' '.join(args)}",
        )

    return RunResult(
        returncode=proc.returncode or 0,
        stdout=stdout_bytes.decode(errors="replace").strip(),
        stderr=stderr_bytes.decode(errors="replace").strip(),
    )
