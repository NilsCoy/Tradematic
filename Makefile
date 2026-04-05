.PHONY: run migrate makemigrations shell collect-static superuser test format lint uv-lock uv-update


# Install deps from lockfile
install:
	uv sync

# Run development server
run:
	uv run python manage.py runserver

# Apply migrations
migrate:
	uv run python manage.py migrate

# Create new migrations
makemigrations:
	uv run python manage.py makemigrations

# Django shell
shell:
	uv run python manage.py shell

# Collect static files
collect-static:
	uv run python manage.py collectstatic --noinput

# Create superuser
superuser:
	uv run python manage.py createsuperuser

# Run tests
test:
	uv run python manage.py test

# Code formatting
format:
	uv run ruff check . --fix
	uv run ruff format .

# Static analysis (lint only)
lint:
	uv run ruff check .

# Update uv lockfile
uv-lock:
	uv lock

# Update all dependencies
uv-update:
	uv sync --upgrade
