# syntax = docker/dockerfile:1
#
# Conductor Backend — two-stage build
# Stage 1: build venv with uv
# Stage 2: runtime with only installed packages

# ── Stage 1: build ──
FROM python:3.14-slim AS builder

WORKDIR /build
COPY pyproject.toml .

RUN pip install --no-cache-dir "uv>=0.5" \
 && uv venv /opt/venv \
 && uv pip install --python /opt/venv/bin/python \
    --no-cache-dir \
    -e ".[dev]" 2>&1

# ── Stage 2: runtime ──
FROM python:3.14-slim

WORKDIR /app

# Install git (needed for workspace operations)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Application code
COPY app/ /app/app/
COPY alembic.ini /app/
COPY alembic/ /app/alembic/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]