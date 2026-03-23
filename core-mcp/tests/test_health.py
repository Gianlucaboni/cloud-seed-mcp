"""Tests for the /health HTTP endpoint."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from core_mcp.server import health_check


@pytest.fixture
def health_app():
    """Minimal Starlette app with only the /health route.

    This avoids pulling in the StreamableHTTPSessionManager (and its
    real MCP lifespan) — we only need to exercise the route handler.
    """
    app = Starlette(routes=[Route("/health", health_check, methods=["GET"])])
    return app


def test_health_returns_200(health_app):
    """GET /health must return HTTP 200."""
    client = TestClient(health_app)
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_json_body(health_app):
    """GET /health must return JSON body {"status": "ok"}."""
    client = TestClient(health_app)
    response = client.get("/health")
    assert response.json() == {"status": "ok"}


def test_health_content_type(health_app):
    """GET /health must set application/json content-type."""
    client = TestClient(health_app)
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]


def test_health_not_found_on_wrong_path(health_app):
    """Paths other than /health must return 404."""
    client = TestClient(health_app)
    response = client.get("/healthz")
    assert response.status_code == 404
