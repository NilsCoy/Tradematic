.DEFAULT_GOAL := help

UV ?= uv
TRADER_PYTHON ?= /opt/homebrew/bin/python3.10
ASSETS ?=
ASSETS_FILE ?=
LIMIT ?= 20
INTERVAL_SECONDS ?= 900
QUESTION ?= Какие события сильнее всего влияют на рынок?
OLLAMA_BASE_MODEL ?= llama3.1
OLLAMA_ANALYST_MODEL ?= tradematic-analyst

NEWS_SERVICE_DIR := services/news_aggregator
EDMI_SERVICE_DIR := services/market_event_engine
DATASETS_DIR := main/scripts/datasets

NEWS_CSV := $(NEWS_SERVICE_DIR)/data/news_dataset.csv
NEWS_CSV_COPY := $(DATASETS_DIR)/news_dataset.csv
PROCESSED_CSV := $(DATASETS_DIR)/processed_events.csv
DEDUP_STATE_CSV := $(DATASETS_DIR)/processed_state.csv
RAG_INDEX_CSV := $(DATASETS_DIR)/rag_index.csv
RAG_TRAINING_JSONL := $(DATASETS_DIR)/rag_training.jsonl
OLLAMA_MODELFILE := $(DATASETS_DIR)/Modelfile.$(OLLAMA_ANALYST_MODEL)
ASSET_ANALYSIS_JSON := $(DATASETS_DIR)/asset_analysis.json
ASSET_ANALYSIS_MD := $(DATASETS_DIR)/asset_analysis.md
MARKET_BRIEF_JSON := $(DATASETS_DIR)/market_brief.json
MARKET_BRIEF_MD := $(DATASETS_DIR)/market_brief.md
DEFAULT_ASSETS_FILE := $(DATASETS_DIR)/assets.txt
EFFECTIVE_ASSETS_FILE := $(if $(ASSETS_FILE),$(ASSETS_FILE),$(if $(wildcard $(DEFAULT_ASSETS_FILE)),$(DEFAULT_ASSETS_FILE),))

EDMI_ENV := EDMI_TRADEMATIC_DATASETS_DIR=$(abspath $(DATASETS_DIR)) EDMI_EMBEDDING_LOCAL_FILES_ONLY=true
ASSET_FLAGS = $(foreach asset,$(ASSETS),--asset $(asset))
ASSET_ARGS = $(if $(EFFECTIVE_ASSETS_FILE),--assets-file $(abspath $(EFFECTIVE_ASSETS_FILE)),$(if $(ASSETS),$(ASSET_FLAGS),))

.PHONY: help install run migrate makemigrations shell collect-static superuser test format lint uv-lock uv-update \
	ollama-check install-services collect-news process-news process-news-scheduled build-rag ollama-model analyze-assets rag-query \
	market-brief analyze-all pipeline pipeline-from-existing-csv scheduled-once schedule clean-pipeline

help:
	@printf "Tradematic commands:\n"
	@printf "  make install                 Install Tradematic Django dependencies\n"
	@printf "  make run                     Run Django development server\n"
	@printf "  make pipeline LIMIT=20       Collect news -> EDMI process -> CSV -> RAG -> Ollama analysis\n"
	@printf "  make pipeline ASSETS_FILE=assets.txt LIMIT=20\n"
	@printf "                               Same pipeline with an explicit asset universe\n"
	@printf "  make pipeline-from-existing-csv LIMIT=20\n"
	@printf "                               Process current parser CSV without collecting\n"
	@printf "  make schedule ASSETS_FILE=assets.txt INTERVAL_SECONDS=900\n"
	@printf "                               Run pipeline forever on an interval with persistent dedup\n"
	@printf "  make collect-news            Run bundled news parser\n"
	@printf "  make process-news LIMIT=20\n"
	@printf "                               Process parser CSV into $(PROCESSED_CSV)\n"
	@printf "  make build-rag               Build CSV-backed RAG index and training JSONL\n"
	@printf "  make ollama-model            Create local $(OLLAMA_ANALYST_MODEL) Ollama model wrapper\n"
	@printf "  make analyze-assets          Generate per-asset analysis with Ollama\n"
	@printf "  make market-brief            Generate categorized market/economic brief\n"
	@printf "  make rag-query QUESTION='...' Query the built RAG index\n"
	@printf "  make ollama-check            Verify local llama3.1\n"

install:
	$(UV) sync --python $(TRADER_PYTHON) --frozen --no-install-package tensorflow-io-gcs-filesystem
	$(UV) pip install cryptography

install-services:
	cd $(NEWS_SERVICE_DIR) && $(UV) sync
	cd $(EDMI_SERVICE_DIR) && $(UV) sync --all-extras --dev

run:
	$(UV) run --no-sync python manage.py runserver 127.0.0.1:8001

migrate:
	$(UV) run --no-sync python manage.py migrate

makemigrations:
	$(UV) run --no-sync python manage.py makemigrations

shell:
	$(UV) run --no-sync python manage.py shell

collect-static:
	$(UV) run --no-sync python manage.py collectstatic --noinput

superuser:
	$(UV) run --no-sync python manage.py createsuperuser

test:
	$(UV) run --no-sync python manage.py test

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
		--file-order \
		--limit $(LIMIT)

process-news-scheduled:
	mkdir -p $(DATASETS_DIR)
	cd $(EDMI_SERVICE_DIR) && $(EDMI_ENV) $(UV) run edmi-export-events \
		--input $(abspath $(NEWS_CSV)) \
		--output $(abspath $(PROCESSED_CSV)) \
		--file-order \
		--limit $(LIMIT) \
		--state-file $(abspath $(DEDUP_STATE_CSV)) \
		--append

build-rag:
	mkdir -p $(DATASETS_DIR)
	cd $(EDMI_SERVICE_DIR) && $(EDMI_ENV) $(UV) run edmi-rag-build \
		--input $(abspath $(PROCESSED_CSV)) \
		--output $(abspath $(RAG_INDEX_CSV)) \
		--training-jsonl $(abspath $(RAG_TRAINING_JSONL))

ollama-model:
	mkdir -p $(DATASETS_DIR)
	cd $(EDMI_SERVICE_DIR) && $(EDMI_ENV) $(UV) run edmi-rag-modelfile \
		--output $(abspath $(OLLAMA_MODELFILE)) \
		--base-model $(OLLAMA_BASE_MODEL)
	ollama create $(OLLAMA_ANALYST_MODEL) -f $(OLLAMA_MODELFILE)

analyze-assets:
	cd $(EDMI_SERVICE_DIR) && $(EDMI_ENV) $(UV) run edmi-rag-analyze \
		--index $(abspath $(RAG_INDEX_CSV)) \
		$(ASSET_ARGS) \
		--model $(OLLAMA_ANALYST_MODEL) \
		--output-json $(abspath $(ASSET_ANALYSIS_JSON)) \
		--output-md $(abspath $(ASSET_ANALYSIS_MD))

market-brief:
	cd $(EDMI_SERVICE_DIR) && $(EDMI_ENV) $(UV) run edmi-rag-brief \
		--index $(abspath $(RAG_INDEX_CSV)) \
		--model $(OLLAMA_ANALYST_MODEL) \
		--output-json $(abspath $(MARKET_BRIEF_JSON)) \
		--output-md $(abspath $(MARKET_BRIEF_MD))

analyze-all: analyze-assets market-brief

rag-query:
	cd $(EDMI_SERVICE_DIR) && $(EDMI_ENV) $(UV) run edmi-rag-query \
		--index $(abspath $(RAG_INDEX_CSV)) \
		--question "$(QUESTION)"

pipeline: collect-news process-news build-rag ollama-model analyze-all
	@printf "\nPipeline completed:\n"
	@printf "  raw news:       $(NEWS_CSV_COPY)\n"
	@printf "  processed CSV:  $(PROCESSED_CSV)\n"
	@printf "  RAG index:      $(RAG_INDEX_CSV)\n"
	@printf "  training JSONL: $(RAG_TRAINING_JSONL)\n"
	@printf "  analysis JSON:  $(ASSET_ANALYSIS_JSON)\n"
	@printf "  analysis MD:    $(ASSET_ANALYSIS_MD)\n"
	@printf "  market brief:   $(MARKET_BRIEF_MD)\n"

pipeline-from-existing-csv: process-news build-rag ollama-model analyze-all
	@printf "\nPipeline completed from existing CSV:\n"
	@printf "  processed CSV:  $(PROCESSED_CSV)\n"
	@printf "  RAG index:      $(RAG_INDEX_CSV)\n"
	@printf "  training JSONL: $(RAG_TRAINING_JSONL)\n"
	@printf "  analysis JSON:  $(ASSET_ANALYSIS_JSON)\n"
	@printf "  analysis MD:    $(ASSET_ANALYSIS_MD)\n"
	@printf "  market brief:   $(MARKET_BRIEF_MD)\n"

scheduled-once: collect-news process-news-scheduled build-rag ollama-model analyze-all
	@printf "\nScheduled iteration completed:\n"
	@printf "  dedup state:    $(DEDUP_STATE_CSV)\n"
	@printf "  processed CSV:  $(PROCESSED_CSV)\n"
	@printf "  RAG index:      $(RAG_INDEX_CSV)\n"
	@printf "  training JSONL: $(RAG_TRAINING_JSONL)\n"
	@printf "  analysis MD:    $(ASSET_ANALYSIS_MD)\n"
	@printf "  market brief:   $(MARKET_BRIEF_MD)\n"

schedule:
	@printf "Starting scheduled Tradematic pipeline every $(INTERVAL_SECONDS) seconds.\n"
	@while true; do \
		$(MAKE) scheduled-once || printf "Scheduled iteration failed; retrying after interval.\n"; \
		printf "Sleeping $(INTERVAL_SECONDS) seconds before next iteration.\n"; \
		sleep $(INTERVAL_SECONDS); \
	done

clean-pipeline:
	rm -f $(NEWS_CSV_COPY) $(PROCESSED_CSV) $(DEDUP_STATE_CSV) $(RAG_INDEX_CSV) $(RAG_TRAINING_JSONL) $(OLLAMA_MODELFILE) $(ASSET_ANALYSIS_JSON) $(ASSET_ANALYSIS_MD) $(MARKET_BRIEF_JSON) $(MARKET_BRIEF_MD)
