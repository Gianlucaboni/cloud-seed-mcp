FROM python:3.12-slim

# System deps for building asyncpg wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project metadata first for layer caching
COPY pyproject.toml ./

# Copy source
COPY src/ src/

# Install the package with dev extras (httpx needed by FastAPI TestClient;
# pytest is also a runtime dep for running generated tool tests)
RUN uv pip install --system ".[dev]"

# Default entrypoint — can be overridden in docker-compose
CMD ["python", "-m", "tool_forge"]
