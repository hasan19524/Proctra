# syntax=docker/dockerfile:1
# Procto backend — FastAPI (REST + WebSocket gateway, meeting core services).
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for asyncpg (libpq) and uv.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast, reproducible resolver).
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# ---- Dependencies layer (cached unless pyproject/lock change) ----
FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ---- Runtime image ----
FROM base AS runtime
WORKDIR /app

# Non-root runtime user.
RUN groupadd --system procto && useradd --system --gid procto --home-dir /app procto

COPY --from=deps /app/.venv /app/.venv
COPY . /app
# Ensure the venv's binaries win on PATH.
ENV PATH="/app/.venv/bin:${PATH}" \
    VIRTUAL_ENV="/app/.venv"

# Drop privileges.
RUN chown -R procto:procto /app
USER procto

EXPOSE 8001

# Alembic migrations run as part of deploy (see docker-compose.prod.yml);
# the container only serves traffic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]