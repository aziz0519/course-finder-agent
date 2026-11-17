# syntax=docker/dockerfile:1.7
#
# Three build targets share one runtime base:
#   api     FastAPI service
#   ui      Gradio frontend
#   worker  on-demand ingestion CLI
#
# CI builds these targets with push disabled. Publishing to ECR is a separate,
# explicit deployment step and is intentionally absent from the M6 workflow.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.13.8

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend
COPY scripts ./scripts
COPY data ./data
COPY ui ./ui

RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home appuser \
    && chown -R appuser:appuser /app

FROM base AS api

RUN uv sync --frozen --no-dev
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS ui

RUN uv sync --frozen --no-dev --group ui
USER appuser
EXPOSE 7860
CMD ["python", "-m", "ui.app"]

FROM base AS worker

RUN uv sync --frozen --no-dev
USER appuser
CMD ["python", "scripts/ingest_datasets.py"]
