"""Tests for tool_forge.generator."""

from __future__ import annotations

import ast

import pytest

from tool_forge.generator import (
    ToolParameter,
    ToolSpec,
    generate_test_code,
    generate_tool_code,
)


class TestGenerateToolCode:
    """Verify the template-based code generator."""

    def test_valid_python(self, sample_spec: ToolSpec) -> None:
        code = generate_tool_code(sample_spec)
        # Must parse without SyntaxError.
        ast.parse(code)

    def test_has_register_function(self, sample_spec: ToolSpec) -> None:
        code = generate_tool_code(sample_spec)
        tree = ast.parse(code)
        func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert "register" in func_names

    def test_has_inner_async_tool_function(self, sample_spec: ToolSpec) -> None:
        code = generate_tool_code(sample_spec)
        tree = ast.parse(code)
        async_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
        assert sample_spec.name in async_names

    def test_imports_run_command(self, sample_spec: ToolSpec) -> None:
        code = generate_tool_code(sample_spec)
        assert "from core_mcp.tools._subprocess import run_command" in code

    def test_imports_fastmcp(self, sample_spec: ToolSpec) -> None:
        code = generate_tool_code(sample_spec)
        assert "from mcp.server.fastmcp import FastMCP" in code

    def test_contains_description(self, sample_spec: ToolSpec) -> None:
        code = generate_tool_code(sample_spec)
        assert sample_spec.description in code

    def test_parameters_in_signature(self, sample_spec: ToolSpec) -> None:
        code = generate_tool_code(sample_spec)
        for param in sample_spec.parameters:
            assert param.name in code

    def test_bare_spec_no_services(self, bare_spec: ToolSpec) -> None:
        code = generate_tool_code(bare_spec)
        ast.parse(code)
        assert "register" in code

    def test_multiple_parameters(self) -> None:
        spec = ToolSpec(
            name="create_bucket",
            description="Create a GCS bucket",
            gcp_services=["storage"],
            parameters=[
                ToolParameter(name="project_id", description="GCP project"),
                ToolParameter(name="bucket_name", description="Bucket name"),
                ToolParameter(name="region", description="Region", default='"us-central1"'),
            ],
        )
        code = generate_tool_code(spec)
        ast.parse(code)
        assert "project_id" in code
        assert "bucket_name" in code
        assert "region" in code
        assert "us-central1" in code


class TestGenerateTestCode:
    """Verify the test code generator."""

    def test_valid_python(self, sample_spec: ToolSpec) -> None:
        tool_code = generate_tool_code(sample_spec)
        test_code = generate_test_code(sample_spec, tool_code)
        ast.parse(test_code)

    def test_contains_test_class(self, sample_spec: ToolSpec) -> None:
        tool_code = generate_tool_code(sample_spec)
        test_code = generate_test_code(sample_spec, tool_code)
        assert "class TestStructure" in test_code

    def test_tests_register_function(self, sample_spec: ToolSpec) -> None:
        tool_code = generate_tool_code(sample_spec)
        test_code = generate_test_code(sample_spec, tool_code)
        assert "test_has_register_function" in test_code

    def test_tests_imports_run_command(self, sample_spec: ToolSpec) -> None:
        tool_code = generate_tool_code(sample_spec)
        test_code = generate_test_code(sample_spec, tool_code)
        assert "test_imports_run_command" in test_code

    def test_parameter_tests_generated(self, sample_spec: ToolSpec) -> None:
        tool_code = generate_tool_code(sample_spec)
        test_code = generate_test_code(sample_spec, tool_code)
        for param in sample_spec.parameters:
            assert f"test_param_{param.name}_in_signature" in test_code
