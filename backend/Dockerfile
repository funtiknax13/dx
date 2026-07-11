# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app

COPY pyproject.toml uv.lock* ./

# ---- dev: compiler stays available for ad-hoc `uv sync` while iterating on
# deps; code is bind-mounted, runs with --reload ----
FROM base AS dev
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-install-project 2>/dev/null || uv sync --no-install-project
COPY . .
RUN uv sync --frozen 2>/dev/null || uv sync
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- builder: compiles C-extension deps (argon2-cffi etc.) into a venv.
# build-essential/gcc live only here and never reach the final prod image. ----
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

# ---- prod: just the compiled venv + app code, no compiler, no bind mount ----
FROM python:3.12-slim AS prod
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /app /app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
