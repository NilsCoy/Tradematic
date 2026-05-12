# syntax=docker/dockerfile:1.7

FROM python:3.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl make libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /uvx /usr/local/bin/

# Dependency layer: copy lockfiles and editable service packages before app code
# so Docker can reuse the expensive ML dependency layer when Django/templates change.
COPY pyproject.toml uv.lock README.md Makefile ./
COPY services ./services

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --python python3.10 --all-groups --frozen --no-install-package tensorflow-io-gcs-filesystem

COPY manage.py main.py ./
COPY invest ./invest
COPY main ./main
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts
COPY docker ./docker

EXPOSE 8000 8001

CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]
