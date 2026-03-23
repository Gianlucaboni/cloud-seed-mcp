"""Tests for the Tool Forge HTTP API (__main__.py).

All database and pipeline calls are mocked so tests run without PostgreSQL,
pytest subprocess, or network access.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tool_forge.__main__ import app
from tool_forge.registry import ToolRecord, ToolStatus, compute_code_hash
from tool_forge.sandbox import SandboxResult
from tool_forge.scanner import Violation
from tool_forge.tester import TestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    name: str = "list_buckets",
    status: str = "staging",
    promoted_at: datetime | None = None,
    source_code: str = "def register(mcp): pass",
) -> ToolRecord:
    return ToolRecord(
        id="00000000-0000-0000-0000-000000000001",
        name=name,
        version="0.1.0",
        description="A test tool",
        schema_json={"type": "object", "properties": {}, "required": []},
        code_hash=compute_code_hash(source_code),
        source_code=source_code,
        status=ToolStatus(status),
        created_at=datetime.now(timezone.utc),
        promoted_at=promoted_at,
    )


_MINIMAL_SPEC: dict[str, Any] = {
    "name": "list_buckets",
    "description": "List GCS buckets",
    "version": "0.1.0",
    "gcp_services": ["storage"],
    "permissions": ["storage.buckets.list"],
    "parameters": [
        {"name": "project_id", "description": "GCP project ID"},
    ],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_pool() -> AsyncMock:
    """A mock asyncpg pool injected into the app state."""
    return AsyncMock()


@pytest.fixture()
def client(mock_pool: AsyncMock) -> TestClient:
    """FastAPI test client with the DB pool pre-seeded."""
    import tool_forge.__main__ as main_mod

    main_mod._pool = mock_pool
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_body_contains_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /generate  — happy path
# ---------------------------------------------------------------------------


class TestGenerateHappyPath:
    @patch("tool_forge.__main__.reg.register_tool")
    @patch("tool_forge.__main__.scanner.scan", return_value=[])
    @patch("tool_forge.__main__.tester.run_tests")
    @patch("tool_forge.__main__.gen.generate_tool_code", return_value="def register(mcp): pass")
    def test_staged_when_all_gates_pass(
        self,
        mock_gen: MagicMock,
        mock_tests: AsyncMock,
        mock_scan: MagicMock,
        mock_register: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_tests.return_value = TestResult(passed=2, failed=0, errors=0, output="2 passed")
        mock_register.return_value = _make_record()

        response = client.post("/generate", json=_MINIMAL_SPEC)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "staged"
        assert body["tests_passed"] is True
        assert body["scan_passed"] is True
        assert body["violations"] == []

    @patch("tool_forge.__main__.reg.register_tool")
    @patch("tool_forge.__main__.scanner.scan", return_value=[])
    @patch("tool_forge.__main__.tester.run_tests")
    @patch("tool_forge.__main__.gen.generate_tool_code", return_value="def register(mcp): pass")
    def test_returns_tool_name_and_version(
        self,
        mock_gen: MagicMock,
        mock_tests: AsyncMock,
        mock_scan: MagicMock,
        mock_register: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_tests.return_value = TestResult(passed=1, failed=0, errors=0, output="1 passed")
        mock_register.return_value = _make_record()

        response = client.post("/generate", json=_MINIMAL_SPEC)
        body = response.json()

        assert body["tool_name"] == "list_buckets"
        assert body["version"] == "0.1.0"
        assert len(body["code_hash"]) == 64  # SHA-256 hex

    @patch("tool_forge.__main__.reg.register_tool")
    @patch("tool_forge.__main__.scanner.scan", return_value=[])
    @patch("tool_forge.__main__.tester.run_tests")
    @patch("tool_forge.__main__.gen.generate_tool_code", return_value="def register(mcp): pass")
    def test_register_called_once(
        self,
        mock_gen: MagicMock,
        mock_tests: AsyncMock,
        mock_scan: MagicMock,
        mock_register: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_tests.return_value = TestResult(passed=1, failed=0, errors=0, output="1 passed")
        mock_register.return_value = _make_record()

        client.post("/generate", json=_MINIMAL_SPEC)
        mock_register.assert_awaited_once()


# ---------------------------------------------------------------------------
# POST /generate  — rejection paths
# ---------------------------------------------------------------------------


class TestGenerateRejection:
    @patch("tool_forge.__main__.scanner.scan", return_value=[])
    @patch("tool_forge.__main__.tester.run_tests")
    @patch("tool_forge.__main__.gen.generate_tool_code", return_value="def register(mcp): pass")
    def test_rejected_when_tests_fail(
        self,
        mock_gen: MagicMock,
        mock_tests: AsyncMock,
        mock_scan: MagicMock,
        client: TestClient,
    ) -> None:
        mock_tests.return_value = TestResult(passed=0, failed=2, errors=0, output="2 failed")

        response = client.post("/generate", json=_MINIMAL_SPEC)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "rejected"
        assert body["tests_passed"] is False
        assert "tests failed" in body["message"]

    @patch("tool_forge.__main__.scanner.scan")
    @patch("tool_forge.__main__.tester.run_tests")
    @patch("tool_forge.__main__.gen.generate_tool_code", return_value="eval('x')")
    def test_rejected_when_scan_fails(
        self,
        mock_gen: MagicMock,
        mock_tests: AsyncMock,
        mock_scan: MagicMock,
        client: TestClient,
    ) -> None:
        mock_tests.return_value = TestResult(passed=2, failed=0, errors=0, output="2 passed")
        mock_scan.return_value = [
            Violation(line=1, col=0, code="S001", description="Use of bare eval() is forbidden")
        ]

        response = client.post("/generate", json=_MINIMAL_SPEC)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "rejected"
        assert body["scan_passed"] is False
        assert len(body["violations"]) == 1
        assert body["violations"][0]["code"] == "S001"

    @patch("tool_forge.__main__.scanner.scan")
    @patch("tool_forge.__main__.tester.run_tests")
    @patch("tool_forge.__main__.gen.generate_tool_code", return_value="eval('x')")
    def test_rejected_message_lists_both_failures(
        self,
        mock_gen: MagicMock,
        mock_tests: AsyncMock,
        mock_scan: MagicMock,
        client: TestClient,
    ) -> None:
        mock_tests.return_value = TestResult(passed=0, failed=1, errors=0, output="1 failed")
        mock_scan.return_value = [
            Violation(line=1, col=0, code="S001", description="bare eval")
        ]

        response = client.post("/generate", json=_MINIMAL_SPEC)
        body = response.json()

        assert body["status"] == "rejected"
        assert "tests failed" in body["message"]
        assert "security violation" in body["message"]

    @patch("tool_forge.__main__.reg.register_tool")
    @patch("tool_forge.__main__.scanner.scan", return_value=[])
    @patch("tool_forge.__main__.tester.run_tests")
    @patch("tool_forge.__main__.gen.generate_tool_code", return_value="def register(mcp): pass")
    def test_registry_error_returns_500(
        self,
        mock_gen: MagicMock,
        mock_tests: AsyncMock,
        mock_scan: MagicMock,
        mock_register: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_tests.return_value = TestResult(passed=1, failed=0, errors=0, output="1 passed")
        mock_register.side_effect = Exception("DB connection lost")

        response = client.post("/generate", json=_MINIMAL_SPEC)
        assert response.status_code == 500
        assert "Registry error" in response.json()["detail"]


# ---------------------------------------------------------------------------
# POST /generate  — input validation
# ---------------------------------------------------------------------------


class TestGenerateValidation:
    def test_missing_name_returns_422(self, client: TestClient) -> None:
        payload = dict(_MINIMAL_SPEC)
        del payload["name"]
        response = client.post("/generate", json=payload)
        assert response.status_code == 422

    def test_missing_description_returns_422(self, client: TestClient) -> None:
        payload = dict(_MINIMAL_SPEC)
        del payload["description"]
        response = client.post("/generate", json=payload)
        assert response.status_code == 422

    def test_empty_services_is_valid(self, client: TestClient) -> None:
        """A tool with no GCP services should still be processable."""
        with (
            patch("tool_forge.__main__.gen.generate_tool_code", return_value="def register(mcp): pass"),
            patch("tool_forge.__main__.tester.run_tests", new_callable=AsyncMock) as mock_tests,
            patch("tool_forge.__main__.scanner.scan", return_value=[]),
            patch("tool_forge.__main__.reg.register_tool", new_callable=AsyncMock) as mock_reg,
        ):
            mock_tests.return_value = TestResult(passed=1, failed=0, errors=0, output="1 passed")
            mock_reg.return_value = _make_record()

            payload = {
                "name": "hello_world",
                "description": "A no-op tool",
                "gcp_services": [],
                "parameters": [],
            }
            response = client.post("/generate", json=payload)
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /promote/{tool_name}  — happy path
# ---------------------------------------------------------------------------


class TestPromoteHappyPath:
    @patch("tool_forge.__main__.reg.promote_tool")
    @patch("tool_forge.__main__.sandbox.run_in_sandbox")
    @patch("tool_forge.__main__.reg.get_tool")
    def test_promotes_staging_tool(
        self,
        mock_get: AsyncMock,
        mock_sandbox: AsyncMock,
        mock_promote: AsyncMock,
        client: TestClient,
    ) -> None:
        now = datetime.now(timezone.utc)
        mock_get.return_value = _make_record(status="staging")
        mock_sandbox.return_value = SandboxResult(returncode=0, stdout="ok", stderr="")
        mock_promote.return_value = _make_record(status="active", promoted_at=now)

        response = client.post("/promote/list_buckets")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "active"
        assert body["promoted_at"] is not None

    @patch("tool_forge.__main__.reg.promote_tool")
    @patch("tool_forge.__main__.sandbox.run_in_sandbox")
    @patch("tool_forge.__main__.reg.get_tool")
    def test_sandbox_called_with_source_code(
        self,
        mock_get: AsyncMock,
        mock_sandbox: AsyncMock,
        mock_promote: AsyncMock,
        client: TestClient,
    ) -> None:
        source = "def register(mcp): pass\n# generated"
        now = datetime.now(timezone.utc)
        mock_get.return_value = _make_record(status="staging", source_code=source)
        mock_sandbox.return_value = SandboxResult(returncode=0, stdout="", stderr="")
        mock_promote.return_value = _make_record(status="active", promoted_at=now)

        client.post("/promote/list_buckets")
        mock_sandbox.assert_awaited_once_with(source)


# ---------------------------------------------------------------------------
# POST /promote/{tool_name}  — failure paths
# ---------------------------------------------------------------------------


class TestPromoteFailures:
    @patch("tool_forge.__main__.reg.get_tool")
    def test_404_when_tool_not_in_staging(
        self,
        mock_get: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_get.return_value = None

        response = client.post("/promote/nonexistent")
        assert response.status_code == 404

    @patch("tool_forge.__main__.reg.get_tool")
    def test_404_when_tool_is_active_not_staging(
        self,
        mock_get: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_get.return_value = _make_record(status="active")

        response = client.post("/promote/list_buckets")
        assert response.status_code == 404

    @patch("tool_forge.__main__.sandbox.run_in_sandbox")
    @patch("tool_forge.__main__.reg.get_tool")
    def test_422_when_sandbox_fails(
        self,
        mock_get: AsyncMock,
        mock_sandbox: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_get.return_value = _make_record(status="staging")
        mock_sandbox.return_value = SandboxResult(
            returncode=1, stdout="", stderr="NameError: name 'x' is not defined"
        )

        response = client.post("/promote/list_buckets")
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Sandbox gate failed" in detail["message"]
        assert detail["returncode"] == 1

    @patch("tool_forge.__main__.reg.promote_tool")
    @patch("tool_forge.__main__.sandbox.run_in_sandbox")
    @patch("tool_forge.__main__.reg.get_tool")
    def test_422_when_registry_promote_raises(
        self,
        mock_get: AsyncMock,
        mock_sandbox: AsyncMock,
        mock_promote: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_get.return_value = _make_record(status="staging")
        mock_sandbox.return_value = SandboxResult(returncode=0, stdout="", stderr="")
        mock_promote.side_effect = ValueError("Tool 'list_buckets' not found in staging status")

        response = client.post("/promote/list_buckets")
        assert response.status_code == 422
        assert "not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /tools
# ---------------------------------------------------------------------------


class TestListTools:
    @patch("tool_forge.__main__.reg.list_tools")
    def test_returns_all_tools(
        self,
        mock_list: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_list.return_value = [
            _make_record(name="tool_a", status="staging"),
            _make_record(name="tool_b", status="active"),
        ]
        response = client.get("/tools")
        assert response.status_code == 200
        assert len(response.json()) == 2

    @patch("tool_forge.__main__.reg.list_tools")
    def test_filter_by_status(
        self,
        mock_list: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_list.return_value = [_make_record(status="active")]
        response = client.get("/tools?status=active")
        assert response.status_code == 200
        assert response.json()[0]["status"] == "active"

    def test_invalid_status_returns_400(self, client: TestClient) -> None:
        response = client.get("/tools?status=unknown")
        assert response.status_code == 400

    @patch("tool_forge.__main__.reg.list_tools")
    def test_empty_registry_returns_empty_list(
        self,
        mock_list: AsyncMock,
        client: TestClient,
    ) -> None:
        mock_list.return_value = []
        response = client.get("/tools")
        assert response.status_code == 200
        assert response.json() == []
