from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from core_mcp.config import Settings
from core_mcp.tools import terraform, github, cloudrun, database


@dataclass
class AppContext:
    settings: Settings


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    settings = Settings()
    # Future: initialize DB pool, OPA client, etc.
    yield AppContext(settings=settings)


mcp = FastMCP(
    "cloud-seed",
    lifespan=app_lifespan,
)

terraform.register(mcp)
github.register(mcp)
cloudrun.register(mcp)
database.register(mcp)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
