FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY apps/backend/pyproject.toml /app/apps/backend/pyproject.toml
COPY apps/backend/README.md /app/apps/backend/README.md
COPY apps/backend/alembic.ini /app/apps/backend/alembic.ini
COPY apps/backend/alembic /app/apps/backend/alembic
COPY apps/backend/src /app/apps/backend/src
COPY controls /app/controls
COPY apps/backend/docker/entrypoint.sh /app/apps/backend/docker/entrypoint.sh

RUN python -m pip install --upgrade pip && \
    pip install -e /app/apps/backend && \
    chmod +x /app/apps/backend/docker/entrypoint.sh

WORKDIR /app/apps/backend

EXPOSE 8000

ENTRYPOINT ["/app/apps/backend/docker/entrypoint.sh"]
