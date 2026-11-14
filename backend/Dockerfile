FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

COPY . ./

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').getcode()==200 else 1)"

# Portable start command (shell form so env vars expand):
# - PORT is injected by PaaS platforms (Render, Cloud Run); defaults to 8000.
#   (App Runner keeps its own explicit run command in apprunner.yaml.)
# - GUNICORN_WORKERS / GUNICORN_THREADS tune per platform RAM:
#     Render free tier (512 MB)  -> 2 workers (the default)
#     App Runner (2 GB)          -> set GUNICORN_WORKERS=4 in the service env
CMD .venv/bin/gunicorn -w ${GUNICORN_WORKERS:-2} --threads ${GUNICORN_THREADS:-4} -b 0.0.0.0:${PORT:-8000} "app:create_app()"
