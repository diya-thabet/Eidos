FROM python:3.11-slim
# ============================================================
# Eidos — Multi-stage Docker Build
# ============================================================
# Targets:
#   client   — production image (slim, no dev tools)
#   internal — development image (pytest, debugpy, reload)
#
# Build:
#   docker build --target client   -t eidos:latest .
#   docker build --target internal -t eidos:internal .
# ============================================================

# ---------- builder stage ----------
FROM python:3.11-slim AS builder
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# ---------- client (production) ----------
FROM python:3.11-slim AS client

LABEL maintainer="Eidos Team"
LABEL description="Eidos - Code Intelligence Platform"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

ENV EIDOS_EDITION=client
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# ---------- internal (development) ----------
FROM client AS internal

RUN pip install --no-cache-dir debugpy pytest ruff mypy

ENV EIDOS_EDITION=internal
ENV EIDOS_AUTH_ENABLED=false

# debugpy port
EXPOSE 5678

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
