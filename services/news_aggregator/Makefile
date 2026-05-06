.PHONY: install install-dev run format lint check

install:
	uv sync

install-dev:
	uv sync --dev

run:
	uv run uvicorn app.main:app --reload

format:
	uv run ruff format .

lint:
	uv run ruff check .

check:
	uv run ruff check . --fix
	uv run ruff format .
