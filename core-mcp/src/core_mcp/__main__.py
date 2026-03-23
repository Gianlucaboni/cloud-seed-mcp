import uvicorn

from core_mcp.config import Settings
from core_mcp.server import mcp

settings = Settings()
app = mcp.streamable_http_app()
uvicorn.run(app, host=settings.host, port=settings.port)
