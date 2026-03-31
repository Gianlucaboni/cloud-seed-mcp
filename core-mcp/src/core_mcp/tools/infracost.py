"""Infracost cost estimation helper for Terraform plans."""

from __future__ import annotations

import json
import logging
import os

from core_mcp.tools._subprocess import run_command

logger = logging.getLogger(__name__)


def infracost_available() -> bool:
    """Check if Infracost is configured (API key present)."""
    return bool(os.environ.get("INFRACOST_API_KEY"))


async def estimate_costs(module_path: str) -> dict[str, float] | None:
    """Run Infracost on a Terraform module and return per-resource monthly costs.

    Args:
        module_path: Absolute path to the Terraform module directory.

    Returns:
        Dictionary mapping Terraform resource address to monthly cost in EUR,
        or None if Infracost is unavailable or fails.
        Resources with null/usage-based costs are included with value 0.0.
    """
    if not infracost_available():
        logger.info("Infracost API key not set, skipping cost estimation")
        return None

    result = await run_command(
        "infracost", "breakdown",
        "--path", module_path,
        "--format", "json",
        "--no-color",
        cwd=module_path,
        timeout=120.0,
    )

    if not result.success:
        logger.warning(
            "Infracost failed (exit %d): %s",
            result.returncode,
            result.stderr[:500],
        )
        return None

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("Infracost output is not valid JSON")
        return None

    return _parse_costs(output)


def _parse_costs(infracost_output: dict) -> dict[str, float]:
    """Extract per-resource monthly costs from Infracost JSON output.

    The Infracost JSON structure is:
        projects[0].breakdown.resources[] with:
            - name: Terraform address (e.g. "google_compute_instance.small_vm")
            - monthlyCost: string like "28.11" or null for usage-based

    Returns dict of {terraform_address: monthly_cost_float}.
    """
    costs: dict[str, float] = {}

    for project in infracost_output.get("projects", []):
        breakdown = project.get("breakdown", {})
        for resource in breakdown.get("resources", []):
            name = resource.get("name", "")
            monthly_cost_str = resource.get("monthlyCost")
            if monthly_cost_str is not None:
                try:
                    costs[name] = float(monthly_cost_str)
                except (ValueError, TypeError):
                    costs[name] = 0.0
            else:
                costs[name] = 0.0

    return costs
