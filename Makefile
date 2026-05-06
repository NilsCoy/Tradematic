.DEFAULT_GOAL := help

UV ?= uv
ASSET ?= SBER
LIMIT ?= 20
QUESTION ?= Какие события сильнее всего влияют на $(ASSET)?

NEWS_SERVICE_DIR := services/news_aggregator
EDMI_SERVICE_DIR := services/market_event_engine
DATASETS_DIR := main/scripts/datasets

NEWS_CSV := $(NEWS_SERVICE_DIR)/data/news_dataset.csv
NEWS_CSV_COPY := $(DATASETS_DIR)/news_dataset.csv
PROCESSED_CSV := $(DATASETS_DIR)/processed_events.csv
RAG_INDEX_CSV := $(DATASETS_DIR)/rag_index.csv
RAG_TRAINING_JSONL := $(DATASETS_DIR)/rag_training.jsonl

EDMI_ENV := EDMI_TRADEMATIC_DATASETS_DIR=$(abspath $(DATASETS_DIR)) EDMI_EMBEDDING_LOCAL_FILES_ONLY=true

.PHONY: help install run migrate makemigrations shell collect-static superuser test format lint uv-lock uv-update \
	ollama-check install-services collect-news process-news build-rag rag-query pipeline pipeline-from-existing-csv clean-pipeline

help:
	@printf "Tradematic commands:\n"
	@printf "  make install                 Install Tradematic Django dependencies\n"
	@printf "  make run                     Run Django development server\n"
	@printf "  make pipeline ASSET=SBER     Collect news -> EDMI process -> CSV -> RAG index\n"
	@printf "  make pipeline-from-existing-csv ASSET=SBER LIMIT=20\n"
	@printf "                               Process current parser CSV without collecting\n"
	@printf "  make collect-news            Run bundled news parser\n"
	@printf "  make process-news ASSET=SBER LIMIT=20\n"
	@printf "                               Process parser CSV into $(PROCESSED_CSV)\n"
	@printf "  make build-rag               Build CSV-backed RAG index and training JSONL\n"
	@printf "  make rag-query QUESTION='...' Query the built RAG index\n"
	@printf "  make ollama-check            Verify local llama3.1\n"

install:
	$(UV) sync

install-services:
	cd $(NEWS_SERVICE_DIR) && $(UV) sync
	cd $(EDMI_SERVICE_DIR) && $(UV) sync --all-extras --dev

run:
	$(UV) run python manage.py runserver

migrate:
	$(UV) run python manage.py migrate

makemigrations:
	$(UV) run python manage.py makemigrations

shell:
	$(UV) run python manage.py shell

collect-static:
	$(UV) run python manage.py collectstatic --noinput

superuser:
	$(UV) run python manage.py createsuperuser

test:
	$(UV) run python manage.py test

format:
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

lint:
	$(UV) run ruff check .

uv-lock:
	$(UV) lock
	cd $(NEWS_SERVICE_DIR) && $(UV) lock
	cd $(EDMI_SERVICE_DIR) && $(UV) lock

uv-update:
	$(UV) sync --upgrade

ollama-check:
	ollama run llama3.1 "Return exactly: ok"

collect-news:
	cd $(NEWS_SERVICE_DIR) && $(UV) run python -c 'import asyncio; from app.service import NewsAggregationService; print(asyncio.run(NewsAggregationService().collect_once()))'
	mkdir -p $(DATASETS_DIR)
	cp $(NEWS_CSV) $(NEWS_CSV_COPY)

process-news:
	mkdir -p $(DATASETS_DIR)
	cd $(EDMI_SERVICE_DIR) && $(EDMI_ENV) $(UV) run edmi-export-events \
		--input $(abspath $(NEWS_CSV)) \
		--output $(abspath $(PROCESSED_CSV)) \
		--asset $(ASSET) \
		--limit $(LIMIT)

build-rag:
	mkdir -p $(DATASETS_DIR)
	cd $(EDMI_SERVICE_DIR) && $(EDMI_ENV) $(UV) run edmi-rag-build \
		--input $(abspath $(PROCESSED_CSV)) \
		--output $(abspath $(RAG_INDEX_CSV)) \
		--training-jsonl $(abspath $(RAG_TRAINING_JSONL))

rag-query:
	cd $(EDMI_SERVICE_DIR) && $(EDMI_ENV) $(UV) run edmi-rag-query \
		--index $(abspath $(RAG_INDEX_CSV)) \
		--question "$(QUESTION)"

pipeline: collect-news process-news build-rag
	@printf "\nPipeline completed:\n"
	@printf "  raw news:       $(NEWS_CSV_COPY)\n"
	@printf "  processed CSV:  $(PROCESSED_CSV)\n"
	@printf "  RAG index:      $(RAG_INDEX_CSV)\n"
	@printf "  training JSONL: $(RAG_TRAINING_JSONL)\n"

pipeline-from-existing-csv: process-news build-rag
	@printf "\nPipeline completed from existing CSV:\n"
	@printf "  processed CSV:  $(PROCESSED_CSV)\n"
	@printf "  RAG index:      $(RAG_INDEX_CSV)\n"
	@printf "  training JSONL: $(RAG_TRAINING_JSONL)\n"

clean-pipeline:
	rm -f $(NEWS_CSV_COPY) $(PROCESSED_CSV) $(RAG_INDEX_CSV) $(RAG_TRAINING_JSONL)
