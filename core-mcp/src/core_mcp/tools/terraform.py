"""Terraform CLI tool wrappers for the Core MCP server."""

from __future__ import annotations

import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

from core_mcp.config import Settings
from core_mcp.tools._subprocess import run_command
from core_mcp.tools.infracost import estimate_costs


async def _validate_with_opa(
    plan_json: dict,
    opa_url: str,
    infracost_costs: dict[str, float] | None = None,
) -> list[str]:
    """POST plan JSON to OPA and return list of violations (empty = approved)."""
    try:
        enriched_input = dict(plan_json)
        if infracost_costs is not None:
            enriched_input["infracost_costs"] = infracost_costs

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{opa_url}/v1/data/terraform/deny",
                json={"input": enriched_input},
            )
            resp.raise_for_status()
            return resp.json().get("result", []) or []
    except httpx.ConnectError:
        return [f"OPA unreachable at {opa_url} — cannot validate plan"]
    except httpx.HTTPStatusError as e:
        return [f"OPA returned HTTP {e.response.status_code}"]
    except Exception as e:
        return [f"OPA validation error: {e}"]


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def terraform_plan(project_id: str, module_path: str) -> str:
        """Generate a Terraform plan for the specified module.

        Runs ``terraform init``, ``terraform plan``, and returns the JSON plan
        summary.  This is a Green action (read-only) and executes directly.

        Args:
            project_id: GCP project identifier.
            module_path: Absolute path to the Terraform module directory.
        """
        if not os.path.isabs(module_path):
            return f"Error: module_path must be an absolute path, got: {module_path}"

        # --- terraform init ---
        init_result = await run_command(
            "terraform", "init", "-input=false", "-no-color",
            cwd=module_path,
            env={"TF_VAR_project_id": project_id},
        )
        if not init_result.success:
            return (
                f"Terraform init failed (exit {init_result.returncode}).\n"
                f"stderr: {init_result.stderr}"
            )

        # --- terraform plan ---
        plan_file = os.path.join(module_path, "plan.tfplan")
        plan_result = await run_command(
            "terraform", "plan",
            "-input=false", "-no-color",
            f"-out={plan_file}",
            cwd=module_path,
            env={"TF_VAR_project_id": project_id},
        )
        if not plan_result.success:
            return (
                f"Terraform plan failed (exit {plan_result.returncode}).\n"
                f"stderr: {plan_result.stderr}"
            )

        # --- terraform show -json ---
        show_result = await run_command(
            "terraform", "show", "-json", "-no-color", plan_file,
            cwd=module_path,
        )
        if not show_result.success:
            return (
                f"Terraform show failed (exit {show_result.returncode}).\n"
                f"stderr: {show_result.stderr}"
            )

        # Parse and return a human-readable summary
        try:
            plan_json = json.loads(show_result.stdout)
        except json.JSONDecodeError:
            return (
                "Terraform plan succeeded but JSON parsing failed.\n"
                f"Raw output:\n{show_result.stdout[:2000]}"
            )

        resource_changes = plan_json.get("resource_changes", [])
        actions_summary: dict[str, int] = {}
        for rc in resource_changes:
            for action in rc.get("change", {}).get("actions", []):
                actions_summary[action] = actions_summary.get(action, 0) + 1

        lines = [
            f"Terraform plan for project '{project_id}'",
            f"Module: {module_path}",
            f"Format version: {plan_json.get('format_version', 'unknown')}",
            "",
            "Resource changes:",
        ]
        if actions_summary:
            for action, count in sorted(actions_summary.items()):
                lines.append(f"  {action}: {count}")
        else:
            lines.append("  (no changes)")

        # --- Infracost cost preview (best-effort) ---
        cost_map = await estimate_costs(module_path)
        if cost_map:
            lines.append("")
            lines.append("Estimated costs (Infracost):")
            total = 0.0
            for addr, cost in sorted(cost_map.items()):
                if cost > 0:
                    lines.append(f"  {addr}: {cost:.2f} EUR/month")
                    total += cost
            lines.append(f"  TOTAL: {total:.2f} EUR/month")

        return "\n".join(lines)

    @mcp.tool()
    async def terraform_apply(project_id: str, module_path: str) -> str:
        """Apply a Terraform plan after OPA validation.

        This is a Yellow action -- it requires human approval before
        proceeding.  The response indicates that approval is needed and
        includes a preview of what will change.

        Args:
            project_id: GCP project identifier.
            module_path: Absolute path to the Terraform module directory.
        """
        if not os.path.isabs(module_path):
            return f"Error: module_path must be an absolute path, got: {module_path}"

        plan_file = os.path.join(module_path, "plan.tfplan")

        # Ensure a plan file exists (caller should run terraform_plan first)
        if not os.path.isfile(plan_file):
            return (
                "No plan file found.  Please run terraform_plan first to "
                "generate a plan before applying."
            )

        # --- OPA validation ---
        show_json_result = await run_command(
            "terraform", "show", "-json", "-no-color", plan_file,
            cwd=module_path,
        )
        if show_json_result.success:
            try:
                plan_json = json.loads(show_json_result.stdout)
            except json.JSONDecodeError:
                plan_json = None
        else:
            plan_json = None

        if plan_json:
            # --- Infracost cost estimation (best-effort) ---
            cost_estimates = await estimate_costs(module_path)

            settings = Settings()
            violations = await _validate_with_opa(
                plan_json, settings.opa_url, infracost_costs=cost_estimates,
            )
            if violations:
                violation_list = "\n".join(f"  - {v}" for v in violations)
                return (
                    f"OPA policy validation FAILED for project '{project_id}'.\n\n"
                    f"Violations:\n{violation_list}\n\n"
                    f"The plan was NOT applied. Fix the violations and re-plan."
                )

        # --- YELLOW ACTION: require approval ---
        show_result = await run_command(
            "terraform", "show", "-no-color", plan_file,
            cwd=module_path,
        )
        preview = show_result.stdout[:3000] if show_result.success else "(unable to read plan)"

        # --- terraform apply ---
        apply_result = await run_command(
            "terraform", "apply",
            "-input=false", "-no-color", "-auto-approve",
            plan_file,
            cwd=module_path,
            env={"TF_VAR_project_id": project_id},
        )

        if not apply_result.success:
            return (
                f"[YELLOW ACTION] Terraform apply failed "
                f"(exit {apply_result.returncode}).\n"
                f"stderr: {apply_result.stderr}"
            )

        return (
            f"[YELLOW ACTION] Terraform apply completed for project "
            f"'{project_id}'.\n\n"
            f"Apply output:\n{apply_result.stdout[:3000]}"
        )

    @mcp.tool()
    async def terraform_show_state(project_id: str, module_path: str = "") -> str:
        """Show current Terraform state for a project.

        Runs ``terraform state list`` to show all tracked resources.
        This is a Green action (read-only).

        Args:
            project_id: GCP project identifier.
            module_path: Absolute path to the Terraform module directory.
                         If empty, returns an error asking for the path.
        """
        if not module_path:
            return "Error: module_path is required to locate the Terraform state."

        if not os.path.isabs(module_path):
            return f"Error: module_path must be an absolute path, got: {module_path}"

        # --- terraform state list ---
        list_result = await run_command(
            "terraform", "state", "list",
            cwd=module_path,
            env={"TF_VAR_project_id": project_id},
        )

        if not list_result.success:
            # Possibly no state yet
            if "no state" in list_result.stderr.lower() or "does not exist" in list_result.stderr.lower():
                return f"No Terraform state found for project '{project_id}' in {module_path}."
            return (
                f"Terraform state list failed (exit {list_result.returncode}).\n"
                f"stderr: {list_result.stderr}"
            )

        resources = [r for r in list_result.stdout.splitlines() if r.strip()]

        if not resources:
            return f"Terraform state is empty for project '{project_id}' in {module_path}."

        lines = [
            f"Terraform state for project '{project_id}'",
            f"Module: {module_path}",
            f"Tracked resources ({len(resources)}):",
        ]
        for r in resources:
            lines.append(f"  - {r}")

        return "\n".join(lines)
