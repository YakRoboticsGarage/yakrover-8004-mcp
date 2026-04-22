# Generic Dockerfile for yakrover-8004-mcp deployments.
# Plugin selection is passed via CMD / fly.toml processes.

FROM python:3.13-slim

# uv for fast dep install
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first for layer caching
COPY pyproject.toml uv.lock* ./
RUN uv sync --extra all --frozen 2>/dev/null || uv sync --extra all

# App source
COPY src ./src
COPY scripts ./scripts

# Bring the venv onto PATH
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# Default CMD runs all discovered plugins; fly.toml overrides for single-plugin deploys.
CMD ["python", "scripts/serve.py", "--port", "8080"]
