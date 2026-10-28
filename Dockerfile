# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps for psycopg / bcrypt, removed in the same layer to keep the image small.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app

RUN pip install --upgrade pip && pip install .

# Drop build tooling — the runtime doesn't need a compiler.
RUN apt-get purge -y --auto-remove build-essential \
 && rm -rf /var/lib/apt/lists/*

# Run as a non-root user. The app never writes outside the database path.
RUN useradd --create-home --uid 10001 bayaan \
 && mkdir -p /data && chown -R bayaan:bayaan /app /data
USER bayaan

ENV DATABASE_URL=sqlite:////data/bayaan.db \
    ENVIRONMENT=production \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 2"]
