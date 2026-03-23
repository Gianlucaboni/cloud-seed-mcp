"""Tool Forge HTTP service entry point.

Exposes a minimal FastAPI server that core-mcp can call to drive the full
tool pipeline:  generate → test → scan → sandbox → registry.

Endpoints
---------
GET  /health
    Returns 200 OK once the service is ready.

POST /generate
    Accepts a ToolSpec JSON payload, runs generate → test → scan, registers
    the result in staging, and returns a PipelineResult.

POST /promote/{tool_name}
    Runs the sandbox gate on a staging tool and promotes it to active if the
    gate passes.  Returns the updated ToolRecord as JSON.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tool_forge import generator as gen
from tool_forge import registry as reg
from tool_forge import sandbox, scanner, tester

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("tool_forge.server")

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


def get_pool() -> asyncpg.Pool:
    """Return the active connection pool, raising if not yet initialised."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised")
    return _pool


# ---------------------------------------------------------------------------
# Lifespan — open/close the DB pool
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _pool
    dsn = os.environ.get("CORE_MCP_DATABASE_URL")
    if dsn:
        logger.info("Connecting to database …")
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        logger.info("Database pool ready")
    else:
        logger.warning(
            "CORE_MCP_DATABASE_URL not set — registry endpoints will be unavailable"
        )
    yield
    if _pool is not None:
        await _pool.close()
        logger.info("Database pool closed")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Tool Forge",
    description="Self-evolving MCP tool pipeline: generate, test, scan, promote.",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ToolParameterIn(BaseModel):
    """A single tool parameter as received from callers."""

    name: str
    description: str
    type_hint: str = "str"
    default: str | None = None


class ToolSpecIn(BaseModel):
    """Full tool specification sent by the caller."""

    name: str
    description: str
    version: str = "0.1.0"
    gcp_services: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    parameters: list[ToolParameterIn] = Field(default_factory=list)


class ViolationOut(BaseModel):
    line: int
    col: int
    code: str
    description: str


class PipelineResult(BaseModel):
    """Result of the generate → test → scan → stage pipeline."""

    tool_name: str
    version: str
    code_hash: str
    status: str  # "staged" | "rejected"
    tests_passed: bool
    scan_passed: bool
    violations: list[ViolationOut]
    test_output: str
    message: str


class ToolRecordOut(BaseModel):
    """A tool_registry row serialised for HTTP responses."""

    id: str
    name: str
    version: str
    description: str | None
    # Named "tool_schema" to avoid shadowing Pydantic's BaseModel.schema_json.
    tool_schema: dict[str, Any]
    code_hash: str
    status: str
    created_at: str
    promoted_at: str | None


def _record_to_out(record: reg.ToolRecord) -> ToolRecordOut:
    return ToolRecordOut(
        id=record.id,
        name=record.name,
        version=record.version,
        description=record.description,
        tool_schema=record.schema_json,
        code_hash=record.code_hash,
        status=record.status.value,
        created_at=record.created_at.isoformat(),
        promoted_at=record.promoted_at.isoformat() if record.promoted_at else None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec_in_to_dataclass(spec_in: ToolSpecIn) -> gen.ToolSpec:
    """Convert the Pydantic request model into the generator dataclass."""
    return gen.ToolSpec(
        name=spec_in.name,
        description=spec_in.description,
        gcp_services=spec_in.gcp_services,
        permissions=spec_in.permissions,
        parameters=[
            gen.ToolParameter(
                name=p.name,
                description=p.description,
                type_hint=p.type_hint,
                default=p.default,
            )
            for p in spec_in.parameters
        ],
    )


def _build_schema(spec_in: ToolSpecIn) -> dict[str, Any]:
    """Build a minimal JSON Schema for the tool's parameters."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in spec_in.parameters:
        properties[p.name] = {
            "type": "string",
            "description": p.description,
        }
        if p.default is None:
            required.append(p.name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", summary="Liveness check")
async def health() -> JSONResponse:
    """Return 200 OK when the service is running."""
    return JSONResponse({"status": "ok"})


@app.post("/generate", response_model=PipelineResult, summary="Run full generation pipeline")
async def generate_tool(spec_in: ToolSpecIn) -> PipelineResult:
    """Generate, test, scan, and register a new MCP tool in staging.

    The pipeline runs three gates:
    1. Code generation from template
    2. Auto-generated pytest suite execution
    3. AST-based security scan

    The tool is registered in staging only when **all three gates pass**.
    If any gate fails, ``status`` is ``"rejected"`` and the tool is not
    stored in the registry.
    """
    spec = _spec_in_to_dataclass(spec_in)

    # Gate 1 — generate
    logger.info("Generating code for tool '%s'", spec.name)
    source_code = gen.generate_tool_code(spec)

    # Gate 2 — test
    logger.info("Running tests for tool '%s'", spec.name)
    test_result = await tester.run_tests(spec, source_code)

    # Gate 3 — security scan
    logger.info("Scanning tool '%s'", spec.name)
    violations = scanner.scan(source_code)
    scan_passed = len(violations) == 0

    violations_out = [
        ViolationOut(
            line=v.line,
            col=v.col,
            code=v.code,
            description=v.description,
        )
        for v in violations
    ]

    if not test_result.success or not scan_passed:
        reasons: list[str] = []
        if not test_result.success:
            reasons.append("tests failed")
        if not scan_passed:
            reasons.append(f"{len(violations)} security violation(s)")
        logger.warning("Tool '%s' rejected: %s", spec.name, "; ".join(reasons))
        return PipelineResult(
            tool_name=spec.name,
            version=spec_in.version,
            code_hash=reg.compute_code_hash(source_code),
            status="rejected",
            tests_passed=test_result.success,
            scan_passed=scan_passed,
            violations=violations_out,
            test_output=test_result.output,
            message="; ".join(reasons),
        )

    # All gates passed — persist to registry
    code_hash = reg.compute_code_hash(source_code)
    schema = _build_schema(spec_in)

    pool = get_pool()
    try:
        await reg.register_tool(
            pool,
            name=spec.name,
            version=spec_in.version,
            description=spec.description,
            schema_json=schema,
            source_code=source_code,
        )
    except Exception as exc:
        logger.error("Failed to register tool '%s': %s", spec.name, exc)
        raise HTTPException(status_code=500, detail=f"Registry error: {exc}") from exc

    logger.info("Tool '%s' staged successfully (hash=%s)", spec.name, code_hash[:12])
    return PipelineResult(
        tool_name=spec.name,
        version=spec_in.version,
        code_hash=code_hash,
        status="staged",
        tests_passed=True,
        scan_passed=True,
        violations=[],
        test_output=test_result.output,
        message="Tool staged successfully — pending promotion.",
    )


@app.post(
    "/promote/{tool_name}",
    response_model=ToolRecordOut,
    summary="Promote a staging tool to active",
)
async def promote_tool(tool_name: str) -> ToolRecordOut:
    """Run the sandbox gate and promote a staging tool to active status.

    Fetches the tool's source code from the registry, executes it in the
    sandbox, and calls ``promote_tool`` only if the sandbox run succeeds.

    Raises 404 if the tool does not exist in staging.
    Raises 422 if the sandbox gate fails.
    """
    pool = get_pool()

    # Fetch the staging record
    record = await reg.get_tool(pool, name=tool_name)
    if record is None or record.status != reg.ToolStatus.STAGING:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found in staging",
        )

    # Gate — sandbox
    source_code = record.source_code or ""
    logger.info("Running sandbox for tool '%s'", tool_name)
    sandbox_result = await sandbox.run_in_sandbox(source_code)
    sandbox_passed = sandbox_result.success

    if not sandbox_passed:
        logger.warning(
            "Sandbox failed for tool '%s': returncode=%d stderr=%s",
            tool_name,
            sandbox_result.returncode,
            sandbox_result.stderr[:200],
        )
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Sandbox gate failed — tool not promoted",
                "returncode": sandbox_result.returncode,
                "stderr": sandbox_result.stderr,
            },
        )

    # Promote
    try:
        updated = await reg.promote_tool(
            pool,
            name=tool_name,
            tests_passed=True,  # already verified during /generate
            scan_passed=True,
            sandbox_passed=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info("Tool '%s' promoted to active", tool_name)
    return _record_to_out(updated)


@app.get(
    "/tools",
    response_model=list[ToolRecordOut],
    summary="List tools in the registry",
)
async def list_tools(status: str | None = None) -> list[ToolRecordOut]:
    """List all tools, optionally filtered by status (staging/active/deprecated)."""
    pool = get_pool()
    filter_status: reg.ToolStatus | None = None
    if status is not None:
        try:
            filter_status = reg.ToolStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Must be one of: staging, active, deprecated",
            )
    records = await reg.list_tools(pool, status=filter_status)
    return [_record_to_out(r) for r in records]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.environ.get("TOOL_FORGE_HOST", "0.0.0.0")
    port = int(os.environ.get("TOOL_FORGE_PORT", "8001"))
    uvicorn.run(
        "tool_forge.__main__:app",
        host=host,
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
