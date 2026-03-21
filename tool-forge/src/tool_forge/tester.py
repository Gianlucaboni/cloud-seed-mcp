"""Auto-generates and runs pytest test files for generated tools.

Writes the test file to a temporary directory, runs pytest in a subprocess,
and returns structured results.
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tool_forge.generator import ToolSpec, generate_test_code


@dataclass(frozen=True)
class TestResult:
    """Structured result from running a tool's test suite."""

    passed: int
    failed: int
    errors: int
    output: str

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0


async def run_tests(
    spec: ToolSpec,
    tool_source: str,
    timeout: float = 60.0,
) -> TestResult:
    """Generate and execute pytest tests for a tool.

    Args:
        spec: The tool specification.
        tool_source: Generated Python source code for the tool.
        timeout: Max seconds to wait for pytest to finish.

    Returns:
        TestResult with pass/fail/error counts and raw output.
    """
    test_source = generate_test_code(spec, tool_source)

    with tempfile.TemporaryDirectory(prefix="toolforge_test_") as tmpdir:
        test_file = Path(tmpdir) / f"test_{spec.name}.py"
        test_file.write_text(test_source)

        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "pytest", str(test_file), "-v", "--tb=short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                output=f"Tests timed out after {timeout}s",
            )
        except FileNotFoundError:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                output="pytest not found on PATH",
            )

        output = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        combined = output + "\n" + stderr

        passed, failed, errors = _parse_pytest_summary(output)

        return TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            output=combined.strip(),
        )


def _parse_pytest_summary(output: str) -> tuple[int, int, int]:
    """Parse the pytest summary line to extract pass/fail/error counts.

    Looks for a line like:  ``=== 5 passed, 1 failed, 0 errors in 0.12s ===``

    Returns:
        (passed, failed, errors) tuple.
    """
    import re

    passed = 0
    failed = 0
    errors = 0

    # Search for the summary line at end of pytest output.
    for line in reversed(output.splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            m_passed = re.search(r"(\d+)\s+passed", line)
            m_failed = re.search(r"(\d+)\s+failed", line)
            m_errors = re.search(r"(\d+)\s+error", line)
            if m_passed:
                passed = int(m_passed.group(1))
            if m_failed:
                failed = int(m_failed.group(1))
            if m_errors:
                errors = int(m_errors.group(1))
            break

    return passed, failed, errors
