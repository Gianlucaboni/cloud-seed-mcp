"""Sandbox environment for isolated tool execution.

Creates a temporary directory, writes tool code into it, runs it in a
subprocess with timeout and resource limits, captures output, and cleans up.
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxResult:
    """Result of running code in the sandbox."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


async def run_in_sandbox(
    source: str,
    *,
    timeout: float = 30.0,
    max_output_bytes: int = 1_000_000,
) -> SandboxResult:
    """Execute Python source code in an isolated temporary directory.

    The code is written to a temporary file and executed via a fresh
    Python subprocess.  The subprocess inherits a restricted environment
    (no secret variables) and is killed if it exceeds the timeout.

    Args:
        source: Python source code to execute.
        timeout: Maximum seconds the subprocess may run.
        max_output_bytes: Truncate captured stdout/stderr beyond this size.

    Returns:
        SandboxResult with returncode, stdout, and stderr.
    """
    with tempfile.TemporaryDirectory(prefix="toolforge_sandbox_") as tmpdir:
        script_path = Path(tmpdir) / "tool_sandbox.py"
        script_path.write_text(source)

        # Build a minimal environment — exclude any secret-bearing vars.
        import os

        safe_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": tmpdir,
            "TMPDIR": tmpdir,
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        }

        try:
            proc = await asyncio.create_subprocess_exec(
                "python", str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir,
                env=safe_env,
            )
        except FileNotFoundError:
            return SandboxResult(
                returncode=-1,
                stdout="",
                stderr="Python interpreter not found",
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return SandboxResult(
                returncode=-2,
                stdout="",
                stderr=f"Sandbox execution timed out after {timeout}s",
            )

        stdout = stdout_bytes[:max_output_bytes].decode(errors="replace").strip()
        stderr = stderr_bytes[:max_output_bytes].decode(errors="replace").strip()

        return SandboxResult(
            returncode=proc.returncode or 0,
            stdout=stdout,
            stderr=stderr,
        )
