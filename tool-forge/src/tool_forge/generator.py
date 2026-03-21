"""Template-based MCP tool code generation.

Takes a tool specification (name, description, GCP services, permissions)
and produces Python source code following the register(mcp) + @mcp.tool() pattern.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Map of GCP service names to the imports they typically need.
_SERVICE_IMPORTS: dict[str, str] = {
    "storage": "import json",
    "bigquery": "import json",
    "firestore": "import json",
    "compute": "import json",
    "cloudrun": "import json",
    "pubsub": "import json",
    "cloudsql": "import json",
}

# Map of GCP services to the CLI command prefix used in run_command calls.
_SERVICE_CLI: dict[str, str] = {
    "storage": "gcloud storage",
    "bigquery": "bq",
    "firestore": "gcloud firestore",
    "compute": "gcloud compute",
    "cloudrun": "gcloud run",
    "pubsub": "gcloud pubsub",
    "cloudsql": "gcloud sql",
}


@dataclass(frozen=True)
class ToolParameter:
    """A single parameter for the generated tool function."""

    name: str
    description: str
    type_hint: str = "str"
    default: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    """Full specification for a tool to be generated."""

    name: str
    description: str
    gcp_services: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    parameters: list[ToolParameter] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract LLM interface (placeholder for future LLM-powered generation)
# ---------------------------------------------------------------------------


class LLMInterface(abc.ABC):
    """Abstract interface for LLM-powered tool generation.

    In the future, an LLM can be used to generate the tool body from a
    natural-language description rather than relying purely on templates.
    """

    @abc.abstractmethod
    async def generate_tool_body(self, spec: ToolSpec) -> list[str]:
        """Return the indented body lines for the tool function.

        Args:
            spec: The tool specification.

        Returns:
            A list of Python source lines (without leading whitespace for the
            function-body indent — the template handles that).
        """


# ---------------------------------------------------------------------------
# Template-based generator
# ---------------------------------------------------------------------------


def _build_parameters_signature(params: list[ToolParameter]) -> str:
    """Build the Python function signature string from parameters."""
    parts: list[str] = []
    for p in params:
        hint = p.type_hint
        if p.default is not None:
            parts.append(f"{p.name}: {hint} = {p.default}")
        else:
            parts.append(f"{p.name}: {hint}")
    return ", ".join(parts)


def _build_body_lines(spec: ToolSpec) -> list[str]:
    """Build a default template body that calls gcloud via run_command."""
    lines: list[str] = []

    if not spec.gcp_services:
        lines.append(f'return "Tool {spec.name} executed successfully."')
        return lines

    service = spec.gcp_services[0]
    cli_prefix = _SERVICE_CLI.get(service, f"gcloud {service}")
    cli_parts = cli_prefix.split()

    # Build a read-only "list" or "describe" call as safe default.
    cmd_parts = ", ".join(f'"{p}"' for p in cli_parts)

    lines.append(f"result = await run_command({cmd_parts}, \"list\", \"--format=json\")")
    lines.append("if not result.success:")
    lines.append(f"    return f\"Error: {{result.stderr}}\"")
    lines.append("return result.stdout")
    return lines


def _collect_imports(spec: ToolSpec) -> list[str]:
    """Collect import statements needed by the generated tool."""
    imports: set[str] = set()
    for svc in spec.gcp_services:
        imp = _SERVICE_IMPORTS.get(svc)
        if imp:
            imports.add(imp)
    return sorted(imports)


def generate_tool_code(spec: ToolSpec) -> str:
    """Generate Python source code for an MCP tool from a specification.

    Args:
        spec: Tool specification with name, description, services, etc.

    Returns:
        Complete Python source code as a string.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("tool_template.py.jinja2")

    return template.render(
        tool_name=spec.name,
        description=spec.description,
        docstring=spec.description,
        imports=_collect_imports(spec),
        parameters=spec.parameters,
        parameters_signature=_build_parameters_signature(spec.parameters),
        body_lines=_build_body_lines(spec),
    )


def generate_test_code(spec: ToolSpec, tool_source: str) -> str:
    """Generate pytest test code that validates a generated tool.

    Args:
        spec: The tool specification.
        tool_source: The generated Python source code to test.

    Returns:
        Complete pytest source code as a string.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("test_template.py.jinja2")

    return template.render(
        tool_name=spec.name,
        parameters=spec.parameters,
        tool_source_repr=repr(tool_source),
    )
