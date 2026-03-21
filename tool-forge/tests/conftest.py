"""Shared fixtures for Tool Forge tests."""

from __future__ import annotations

import pytest

from tool_forge.generator import ToolParameter, ToolSpec


@pytest.fixture()
def sample_spec() -> ToolSpec:
    """A minimal tool specification used across tests."""
    return ToolSpec(
        name="list_buckets",
        description="List GCS buckets in a project",
        gcp_services=["storage"],
        permissions=["storage.buckets.list"],
        parameters=[
            ToolParameter(name="project_id", description="GCP project identifier"),
        ],
    )


@pytest.fixture()
def bare_spec() -> ToolSpec:
    """A tool spec with no GCP services (simplest case)."""
    return ToolSpec(
        name="hello_world",
        description="A minimal hello-world tool",
        parameters=[],
    )
