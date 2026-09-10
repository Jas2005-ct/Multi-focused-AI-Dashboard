FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Copy dependency metadata first for Docker layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies from uv.lock into .venv (frozen = reproducible)
RUN uv sync --frozen --no-cache

# Copy application code
COPY . ./

EXPOSE 8000

# Run with gunicorn from the uv virtualenv
CMD [".venv/bin/gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:create_app()"]
