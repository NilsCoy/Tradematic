.DEFAULT_GOAL := help

PYTHON_VERSION ?= 3.13
UV ?= uv
HOST ?= 127.0.0.1
PORT ?= 8000
CSV ?=
ASSET ?=
LIMIT ?= 5
COLLECT ?=
EDMI_URL ?= http://127.0.0.1:8000
NEWS_AGGREGATOR_DIR ?= ../news_aggregator

.PHONY: help python sync sync-core lock test compile api worker ingest parser-api parser-collect ingest-parser pipeline pipeline-local docker-up docker-down docker-logs clean

help:
	@printf "EDMI commands:\n"
	@printf "  make python       Install/select Python $(PYTHON_VERSION) with uv\n"
	@printf "  make sync         Sync dev environment with all extras\n"
	@printf "  make sync-core    Sync only core runtime dependencies\n"
	@printf "  make lock         Refresh uv.lock\n"
	@printf "  make test         Run pytest\n"
	@printf "  make compile      Compile Python files\n"
	@printf "  make api          Run FastAPI on $(HOST):$(PORT)\n"
	@printf "  make worker       Run ARQ worker\n"
	@printf "  make ingest CSV=path [ASSET=AAPL]  Enqueue CSV ingestion\n"
	@printf "  make parser-api   Run sibling news_aggregator API\n"
	@printf "  make parser-collect  Run one news_aggregator collection pass\n"
	@printf "  make ingest-parser ASSET=SBER [LIMIT=5]  Ingest parser CSV into EDMI API\n"
	@printf "  make pipeline ASSET=SBER [LIMIT=5] [COLLECT=1]  Run parser-to-EDMI pipeline through API\n"
	@printf "  make pipeline-local ASSET=SBER [LIMIT=5] [COLLECT=1]  Run direct CLI pipeline\n"
	@printf "  make docker-up    Start Docker Compose stack\n"
	@printf "  make docker-down  Stop Docker Compose stack\n"
	@printf "  make clean        Remove local caches\n"

python:
	$(UV) python install $(PYTHON_VERSION)

sync:
	$(UV) sync --all-extras --dev

sync-core:
	$(UV) sync

lock:
	$(UV) lock

test:
	$(UV) run pytest

compile:
	$(UV) run python -m compileall edmi tests

api:
	$(UV) run uvicorn edmi.api.main:create_app --factory --reload --host $(HOST) --port $(PORT)

worker:
	$(UV) run arq edmi.infrastructure.worker.WorkerSettings

ingest:
	@test -n "$(CSV)" || (printf "CSV is required: make ingest CSV=path/to/news.csv [ASSET=AAPL]\n" && exit 1)
	$(UV) run edmi-ingest $(CSV) $(if $(ASSET),--asset $(ASSET),)

parser-api:
	cd $(NEWS_AGGREGATOR_DIR) && $(UV) run uvicorn app.main:app --reload --host $(HOST) --port 8100

parser-collect:
	cd $(NEWS_AGGREGATOR_DIR) && $(UV) run python -c 'import asyncio; from app.service import NewsAggregationService; print(asyncio.run(NewsAggregationService().collect_once()))'

ingest-parser:
	@test -n "$(ASSET)" || (printf "ASSET is required: make ingest-parser ASSET=SBER [LIMIT=5]\n" && exit 1)
	curl -sS -X POST "$(EDMI_URL)/ingest/news-aggregator" -H "Content-Type: application/json" -d '{"assets":["$(ASSET)"],"limit":$(LIMIT)}'

pipeline:
	@test -n "$(ASSET)" || (printf "ASSET is required: make pipeline ASSET=SBER [LIMIT=5] [COLLECT=1]\n" && exit 1)
	curl -sS -X POST "$(EDMI_URL)/pipeline/news-aggregator" -H "Content-Type: application/json" -d '{"assets":["$(ASSET)"],"limit":$(LIMIT),"collect":$(if $(COLLECT),true,false)}'

pipeline-local:
	@test -n "$(ASSET)" || (printf "ASSET is required: make pipeline ASSET=SBER [LIMIT=5] [COLLECT=1]\n" && exit 1)
	$(UV) run edmi-pipeline --asset $(ASSET) --limit $(LIMIT) $(if $(COLLECT),--collect,)

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache
