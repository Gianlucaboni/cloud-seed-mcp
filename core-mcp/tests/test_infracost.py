"""Tests for the Infracost cost estimation helper."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from core_mcp.tools._subprocess import RunResult
from core_mcp.tools.infracost import _parse_costs, estimate_costs, infracost_available


# ---------------------------------------------------------------------------
# infracost_available
# ---------------------------------------------------------------------------

class TestInfracostAvailable:
    def test_returns_true_when_key_set(self):
        with patch.dict("os.environ", {"INFRACOST_API_KEY": "test-key"}):
            assert infracost_available() is True

    def test_returns_false_when_key_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            assert infracost_available() is False

    def test_returns_false_when_key_empty(self):
        with patch.dict("os.environ", {"INFRACOST_API_KEY": ""}):
            assert infracost_available() is False


# ---------------------------------------------------------------------------
# _parse_costs
# ---------------------------------------------------------------------------

class TestParseCosts:
    def test_parses_resources_with_monthly_costs(self):
        output = {
            "projects": [{
                "breakdown": {
                    "resources": [
                        {"name": "google_compute_instance.web", "monthlyCost": "28.11"},
                        {"name": "google_sql_database_instance.db", "monthlyCost": "221.55"},
                    ]
                }
            }]
        }
        result = _parse_costs(output)
        assert result == {
            "google_compute_instance.web": 28.11,
            "google_sql_database_instance.db": 221.55,
        }

    def test_null_monthly_cost_becomes_zero(self):
        output = {
            "projects": [{
                "breakdown": {
                    "resources": [
                        {"name": "google_storage_bucket.data", "monthlyCost": None},
                    ]
                }
            }]
        }
        result = _parse_costs(output)
        assert result == {"google_storage_bucket.data": 0.0}

    def test_empty_projects(self):
        assert _parse_costs({"projects": []}) == {}

    def test_missing_breakdown(self):
        assert _parse_costs({"projects": [{}]}) == {}

    def test_missing_resources(self):
        assert _parse_costs({"projects": [{"breakdown": {}}]}) == {}

    def test_invalid_cost_string_becomes_zero(self):
        output = {
            "projects": [{
                "breakdown": {
                    "resources": [
                        {"name": "google_compute_instance.web", "monthlyCost": "not-a-number"},
                    ]
                }
            }]
        }
        result = _parse_costs(output)
        assert result == {"google_compute_instance.web": 0.0}


# ---------------------------------------------------------------------------
# estimate_costs
# ---------------------------------------------------------------------------

class TestEstimateCosts:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await estimate_costs("/tmp/tf")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_costs_on_success(self):
        infracost_output = json.dumps({
            "projects": [{
                "breakdown": {
                    "resources": [
                        {"name": "google_compute_instance.web", "monthlyCost": "28.11"}
                    ]
                }
            }]
        })
        with (
            patch.dict("os.environ", {"INFRACOST_API_KEY": "test-key"}),
            patch(
                "core_mcp.tools.infracost.run_command",
                new_callable=AsyncMock,
                return_value=RunResult(0, infracost_output, ""),
            ) as mock_cmd,
        ):
            result = await estimate_costs("/tmp/tf")

        assert result == {"google_compute_instance.web": 28.11}
        mock_cmd.assert_called_once()
        # Verify --currency EUR is passed
        call_args = mock_cmd.call_args
        assert "--currency" in call_args.args
        assert "EUR" in call_args.args

    @pytest.mark.asyncio
    async def test_returns_none_on_command_failure(self):
        with (
            patch.dict("os.environ", {"INFRACOST_API_KEY": "test-key"}),
            patch(
                "core_mcp.tools.infracost.run_command",
                new_callable=AsyncMock,
                return_value=RunResult(1, "", "infracost error"),
            ),
        ):
            result = await estimate_costs("/tmp/tf")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_invalid_json(self):
        with (
            patch.dict("os.environ", {"INFRACOST_API_KEY": "test-key"}),
            patch(
                "core_mcp.tools.infracost.run_command",
                new_callable=AsyncMock,
                return_value=RunResult(0, "NOT JSON", ""),
            ),
        ):
            result = await estimate_costs("/tmp/tf")

        assert result is None
