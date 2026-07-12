# syntax = docker/dockerfile:1

# ── Stage 1: build ──
FROM python:3.14-slim AS builder

WORKDIR /build
COPY pyproject.toml .

RUN pip install --no-cache-dir "uv>=0.5" \
 && uv export --format requirements-txt --no-dev > requirements.txt

# ── Stage 2: runtime ──
FROM python:3.14-slim

WORKDIR /app

# Install runtime deps
COPY --from=builder /build/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY app/ /app/app/
COPY alembic.ini /app/
COPY alembic/ /app/alembic/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
