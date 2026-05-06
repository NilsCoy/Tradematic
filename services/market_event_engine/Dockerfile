FROM python:3.13-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md ./
COPY edmi ./edmi
COPY migrations ./migrations

RUN uv sync --frozen --no-dev --extra postgres

CMD ["uvicorn", "edmi.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
