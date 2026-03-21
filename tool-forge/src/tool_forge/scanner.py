"""AST-based security scanner for generated Python tool code.

Analyses the Abstract Syntax Tree to detect dangerous patterns:
- Bare eval() / exec() calls
- Direct subprocess usage (must use the _subprocess.py wrapper)
- Filesystem access outside allowed paths
- Unauthorized network calls (raw socket, urllib, requests)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    """A single security violation found in tool source code."""

    line: int
    col: int
    code: str
    description: str

    def __str__(self) -> str:
        return f"L{self.line}:{self.col} [{self.code}] {self.description}"


# ---------------------------------------------------------------------------
# Visitor
# ---------------------------------------------------------------------------

# Names that indicate direct subprocess usage (must use run_command wrapper).
_FORBIDDEN_SUBPROCESS_NAMES = frozenset({
    "subprocess",
    "Popen",
    "call",
    "check_call",
    "check_output",
    "run",
})

# Modules that perform raw network I/O outside of the sanctioned patterns.
_FORBIDDEN_NETWORK_MODULES = frozenset({
    "socket",
    "urllib",
    "urllib.request",
    "requests",
    "http.client",
})

# Filesystem functions that write or delete.
_FORBIDDEN_FS_ATTRS = frozenset({
    "rmtree",
    "unlink",
    "remove",
    "rmdir",
    "rename",
    "replace",
})


class _SecurityVisitor(ast.NodeVisitor):
    """Walk the AST and collect security violations."""

    def __init__(self) -> None:
        self.violations: list[Violation] = []

    # -- eval / exec --------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func

        # Bare eval(...) or exec(...)
        if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
            self.violations.append(
                Violation(
                    line=node.lineno,
                    col=node.col_offset,
                    code="S001",
                    description=f"Use of bare {func.id}() is forbidden",
                )
            )

        # subprocess.run / subprocess.Popen etc.
        if isinstance(func, ast.Attribute):
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
                and func.attr in _FORBIDDEN_SUBPROCESS_NAMES
            ):
                self.violations.append(
                    Violation(
                        line=node.lineno,
                        col=node.col_offset,
                        code="S002",
                        description=(
                            f"Direct subprocess.{func.attr}() call — "
                            "use core_mcp.tools._subprocess.run_command instead"
                        ),
                    )
                )

            # os.remove / os.unlink / shutil.rmtree etc.
            if func.attr in _FORBIDDEN_FS_ATTRS:
                self.violations.append(
                    Violation(
                        line=node.lineno,
                        col=node.col_offset,
                        code="S003",
                        description=(
                            f"Forbidden filesystem operation: {func.attr}() — "
                            "generated tools must not modify the filesystem directly"
                        ),
                    )
                )

        # os.system(...)
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr == "system"
        ):
            self.violations.append(
                Violation(
                    line=node.lineno,
                    col=node.col_offset,
                    code="S002",
                    description="os.system() is forbidden — use run_command wrapper",
                )
            )

        self.generic_visit(node)

    # -- imports ------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name == "subprocess":
                self.violations.append(
                    Violation(
                        line=node.lineno,
                        col=node.col_offset,
                        code="S002",
                        description=(
                            "Importing subprocess directly is forbidden — "
                            "use core_mcp.tools._subprocess.run_command"
                        ),
                    )
                )
            if alias.name in _FORBIDDEN_NETWORK_MODULES:
                self.violations.append(
                    Violation(
                        line=node.lineno,
                        col=node.col_offset,
                        code="S004",
                        description=(
                            f"Importing {alias.name} is forbidden — "
                            "network access must go through sanctioned helpers"
                        ),
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        if module == "subprocess" or module.startswith("subprocess."):
            self.violations.append(
                Violation(
                    line=node.lineno,
                    col=node.col_offset,
                    code="S002",
                    description=(
                        "Importing from subprocess is forbidden — "
                        "use core_mcp.tools._subprocess.run_command"
                    ),
                )
            )
        root_module = module.split(".")[0] if module else ""
        if root_module in _FORBIDDEN_NETWORK_MODULES or module in _FORBIDDEN_NETWORK_MODULES:
            self.violations.append(
                Violation(
                    line=node.lineno,
                    col=node.col_offset,
                    code="S004",
                    description=(
                        f"Importing from {module} is forbidden — "
                        "network access must go through sanctioned helpers"
                    ),
                )
            )
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan(source: str) -> list[Violation]:
    """Scan Python source code for security violations.

    Args:
        source: Complete Python source code as a string.

    Returns:
        List of Violation objects (empty means clean).

    Raises:
        SyntaxError: If the source is not valid Python.
    """
    tree = ast.parse(source)
    visitor = _SecurityVisitor()
    visitor.visit(tree)
    return visitor.violations
