import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from core_mcp.config import Settings
from core_mcp.tool_loader import load_tools_from_registry, poll_registry
from core_mcp.tools import terraform, github, cloudrun, database

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    db_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    settings = Settings()
    db_pool: asyncpg.Pool | None = None
    poll_task: asyncio.Task | None = None

    try:
        db_pool = await asyncpg.create_pool(settings.database_url)
        loaded_tools: set[str] = set()
        loaded = await load_tools_from_registry(
            db_pool, server, loaded_tools=loaded_tools,
        )
        logger.info("Loaded %d dynamic tool(s) from registry", loaded)
        poll_task = asyncio.create_task(
            poll_registry(db_pool, server, loaded_tools),
        )
    except Exception:
        logger.warning(
            "Could not connect to state-store or load dynamic tools. "
            "Continuing with built-in tools only.",
            exc_info=True,
        )

    try:
        yield AppContext(settings=settings, db_pool=db_pool)
    finally:
        if poll_task is not None:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
        if db_pool is not None:
            await db_pool.close()


mcp = FastMCP(
    "cloud-seed",
    lifespan=app_lifespan,
)

terraform.register(mcp)
github.register(mcp)
cloudrun.register(mcp)
database.register(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Docker Compose and load balancer probes."""
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
