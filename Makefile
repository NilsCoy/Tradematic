.DEFAULT_GOAL := help

UV ?= uv
ifeq ($(OS),Windows_NT)
PLATFORM := windows
TRADER_PYTHON ?= 3.10
VENV_PYTHON := .venv/Scripts/python.exe
VENV_BIN := .venv/Scripts
define MKDIR_P
powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path '$(subst /,\,$(1))' | Out-Null"
endef
define CP_FILE
powershell -NoProfile -Command "Copy-Item -Force '$(subst /,\,$(1))' '$(subst /,\,$(2))'"
endef
define RM_FILES
powershell -NoProfile -Command "Remove-Item -Force -ErrorAction SilentlyContinue $(foreach path,$(1),'$(subst /,\,$(path))')"
endef
define RM_DIR
powershell -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue '$(subst /,\,$(1))'"
endef
EDMI_RUN = set EDMI_TRADEMATIC_DATASETS_DIR=$(abspath $(DATASETS_DIR))&& set EDMI_EMBEDDING_LOCAL_FILES_ONLY=true&& set RAGPIPE_CHAT_TIMEOUT=$(RAGPIPE_CHAT_TIMEOUT)&& set RAGPIPE_CHAT_CONTEXT_CHARS=$(RAGPIPE_CHAT_CONTEXT_CHARS)&& set RAGPIPE_CHAT_NUM_PREDICT=$(RAGPIPE_CHAT_NUM_PREDICT)&& $(UV)
DOCKER_ENV_PIPELINE = set PIPELINE_LIMIT=$(LIMIT)&&
DOCKER_ENV_PIPELINE_EXISTING = set PIPELINE_LIMIT=$(LIMIT)&& set PIPELINE_MODE=existing-csv&&
DOCKER_ENV_SCHEDULE = set PIPELINE_LIMIT=$(LIMIT)&& set PIPELINE_MODE=schedule&&
else
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
PLATFORM := macos
TRADER_PYTHON ?= python3.10
else
PLATFORM := linux
TRADER_PYTHON ?= python3.10
endif
VENV_PYTHON := .venv/bin/python
VENV_BIN := .venv/bin
define MKDIR_P
mkdir -p $(1)
endef
define CP_FILE
cp $(1) $(2)
endef
define RM_FILES
rm -f $(1)
endef
define RM_DIR
rm -rf $(1)
endef
EDMI_RUN = EDMI_TRADEMATIC_DATASETS_DIR=$(abspath $(DATASETS_DIR)) EDMI_EMBEDDING_LOCAL_FILES_ONLY=true RAGPIPE_CHAT_TIMEOUT=$(RAGPIPE_CHAT_TIMEOUT) RAGPIPE_CHAT_CONTEXT_CHARS=$(RAGPIPE_CHAT_CONTEXT_CHARS) RAGPIPE_CHAT_NUM_PREDICT=$(RAGPIPE_CHAT_NUM_PREDICT) $(UV)
DOCKER_ENV_PIPELINE = PIPELINE_LIMIT=$(LIMIT)
DOCKER_ENV_PIPELINE_EXISTING = PIPELINE_LIMIT=$(LIMIT) PIPELINE_MODE=existing-csv
DOCKER_ENV_SCHEDULE = PIPELINE_LIMIT=$(LIMIT) PIPELINE_MODE=schedule
endif

ASSETS ?=
ASSETS_FILE ?=
LIMIT ?= 20
RAGPIPE_MAX_DOCUMENTS ?= 80
INTERVAL_SECONDS ?= 900
QUESTION ?= Какие события сильнее всего влияют на рынок?
TOP_K ?= 4
RAGPIPE_CHAT_TIMEOUT ?= 600
RAGPIPE_CHAT_CONTEXT_CHARS ?= 900
RAGPIPE_CHAT_NUM_PREDICT ?= 384
OLLAMA_BASE_MODEL ?= llama3.1
OLLAMA_ANALYST_MODEL ?= tradematic-analyst
OLLAMA_URL ?= $(if $(EDMI_OLLAMA_URL),$(EDMI_OLLAMA_URL),http://localhost:11434)

NEWS_SERVICE_DIR := services/news_aggregator
EDMI_SERVICE_DIR := services/market_event_engine
DATASETS_DIR := main/scripts/datasets

NEWS_CSV := $(NEWS_SERVICE_DIR)/data/news_dataset.csv
NEWS_CSV_COPY := $(DATASETS_DIR)/news_dataset.csv
PROCESSED_CSV := $(DATASETS_DIR)/processed_events.csv
DEDUP_STATE_CSV := $(DATASETS_DIR)/processed_state.csv
RAG_INDEX_CSV := $(DATASETS_DIR)/rag_index.csv
RAG_TRAINING_JSONL := $(DATASETS_DIR)/rag_training.jsonl
RAGPIPE_INDEX_DIR := $(DATASETS_DIR)/ragpipe
OLLAMA_MODELFILE := $(DATASETS_DIR)/Modelfile.$(OLLAMA_ANALYST_MODEL)
ASSET_ANALYSIS_JSON := $(DATASETS_DIR)/asset_analysis.json
ASSET_ANALYSIS_MD := $(DATASETS_DIR)/asset_analysis.md
MARKET_BRIEF_JSON := $(DATASETS_DIR)/market_brief.json
MARKET_BRIEF_MD := $(DATASETS_DIR)/market_brief.md
DEFAULT_ASSETS_FILE := $(DATASETS_DIR)/assets.txt
EFFECTIVE_ASSETS_FILE := $(if $(ASSETS_FILE),$(ASSETS_FILE),$(if $(wildcard $(DEFAULT_ASSETS_FILE)),$(DEFAULT_ASSETS_FILE),))

ASSET_FLAGS = $(foreach asset,$(ASSETS),--asset $(asset))
ASSET_ARGS = $(if $(EFFECTIVE_ASSETS_FILE),--assets-file $(abspath $(EFFECTIVE_ASSETS_FILE)),$(if $(ASSETS),$(ASSET_FLAGS),))
RAGPIPE_CSV_INPUT_ARGS = $(if $(wildcard $(PROCESSED_CSV)),--input $(abspath $(PROCESSED_CSV)),) $(if $(wildcard $(RAG_INDEX_CSV)),--input $(abspath $(RAG_INDEX_CSV)),) --input $(abspath $(NEWS_CSV))
RAGPIPE_TEXT_INPUT_ARGS = $(if $(wildcard $(ASSET_ANALYSIS_MD)),--text-input $(abspath $(ASSET_ANALYSIS_MD)),) $(if $(wildcard $(ASSET_ANALYSIS_JSON)),--text-input $(abspath $(ASSET_ANALYSIS_JSON)),) $(if $(wildcard $(MARKET_BRIEF_MD)),--text-input $(abspath $(MARKET_BRIEF_MD)),) $(if $(wildcard $(MARKET_BRIEF_JSON)),--text-input $(abspath $(MARKET_BRIEF_JSON)),)

.PHONY: help config install run migrate makemigrations shell collect-static superuser test format lint uv-lock uv-update \
	ollama-check install-services collect-news process-news process-news-scheduled build-rag ollama-model analyze-assets rag-query \
	build-ragpipe ragpipe-query ragpipe-chat ragpipe-stream market-brief analyze-all pipeline pipeline-from-existing-csv \
	scheduled-once schedule clean-pipeline docker-build docker-up docker-pipeline docker-pipeline-existing docker-schedule \
	docker-smoke docker-down docker-logs

help:
	@printf "Tradematic commands:\n"
	@printf "  make config                  Show detected OS and command configuration\n"
	@printf "  make install                 Install Tradematic Django dependencies\n"
	@printf "  make run                     Run Django development server\n"
	@printf "  make run-edmi                Run local EDMI API for Tradematic chat\n"
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
	@printf "  make build-ragpipe           Build shared BM25+FAISS+Chroma RAG from raw news and EDMI outputs\n"
	@printf "  make ollama-model            Create local $(OLLAMA_ANALYST_MODEL) Ollama model wrapper\n"
	@printf "  make analyze-assets          Generate per-asset analysis with Ollama\n"
	@printf "  make market-brief            Generate categorized market/economic brief\n"
	@printf "  make rag-query QUESTION='...' Query the built RAG index\n"
	@printf "  make ragpipe-stream QUESTION='...' Stream hybrid RAG answer from Ollama\n"
	@printf "  make ollama-check            Verify local llama3.1\n"
	@printf "  make docker-up               Build and run web/API/Redis/Postgres/Ollama UI\n"
	@printf "  make docker-pipeline LIMIT=5 Run one Docker pipeline iteration\n"
	@printf "  make docker-pipeline-existing LIMIT=5\n"
	@printf "                               Run Docker EDMI/RAG pipeline from current parser CSV\n"
	@printf "  make docker-smoke            Run Docker integration smoke checks\n"

config:
	@printf "Platform:        $(PLATFORM)\n"
	@printf "uv command:      $(UV)\n"
	@printf "Python selector: $(TRADER_PYTHON)\n"
	@printf "Venv python:     $(VENV_PYTHON)\n"
	@printf "Venv bin:        $(VENV_BIN)\n"
	@printf "Datasets dir:    $(DATASETS_DIR)\n"

install:
	$(UV) sync --python $(TRADER_PYTHON) --all-groups --frozen --no-install-package tensorflow-io-gcs-filesystem

install-services:
	$(MAKE) install

run:
	$(UV) run --no-sync python manage.py runserver 127.0.0.1:8001

run-edmi:
	$(EDMI_RUN) run --no-sync uvicorn edmi.api.main:create_app --factory --host 127.0.0.1 --port 8000

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

uv-update:
	$(UV) sync --all-groups --upgrade --no-install-package tensorflow-io-gcs-filesystem

ollama-check:
	ollama run llama3.1 "Return exactly: ok"

collect-news:
	$(UV) run --no-sync python -c "import asyncio; from app.service import NewsAggregationService; print(asyncio.run(NewsAggregationService().collect_once()))"
	$(call MKDIR_P,$(DATASETS_DIR))
	$(call CP_FILE,$(NEWS_CSV),$(NEWS_CSV_COPY))

process-news:
	$(call MKDIR_P,$(DATASETS_DIR))
	$(EDMI_RUN) run --no-sync edmi-export-events \
		--input $(abspath $(NEWS_CSV)) \
		--output $(abspath $(PROCESSED_CSV)) \
		--limit $(LIMIT)

process-news-scheduled:
	$(call MKDIR_P,$(DATASETS_DIR))
	$(EDMI_RUN) run --no-sync edmi-export-events \
		--input $(abspath $(NEWS_CSV)) \
		--output $(abspath $(PROCESSED_CSV)) \
		--limit $(LIMIT) \
		--state-file $(abspath $(DEDUP_STATE_CSV)) \
		--append

build-rag:
	$(call MKDIR_P,$(DATASETS_DIR))
	$(EDMI_RUN) run --no-sync edmi-rag-build \
		--input $(abspath $(PROCESSED_CSV)) \
		--output $(abspath $(RAG_INDEX_CSV)) \
		--training-jsonl $(abspath $(RAG_TRAINING_JSONL))

build-ragpipe:
	$(call MKDIR_P,$(RAGPIPE_INDEX_DIR))
	$(EDMI_RUN) run --no-sync edmi-ragpipe-build \
		$(RAGPIPE_CSV_INPUT_ARGS) \
		$(RAGPIPE_TEXT_INPUT_ARGS) \
		--output-dir $(abspath $(RAGPIPE_INDEX_DIR)) \
		--limit $(LIMIT) \
		--max-documents $(RAGPIPE_MAX_DOCUMENTS)

ollama-model:
	$(call MKDIR_P,$(DATASETS_DIR))
	$(EDMI_RUN) run --no-sync edmi-rag-modelfile \
		--output $(abspath $(OLLAMA_MODELFILE)) \
		--base-model $(OLLAMA_BASE_MODEL)
	$(UV) run --no-sync python scripts/create_ollama_model.py \
		--model $(OLLAMA_ANALYST_MODEL) \
		--modelfile $(abspath $(OLLAMA_MODELFILE)) \
		--ollama-url "$(OLLAMA_URL)"

analyze-assets:
	$(EDMI_RUN) run --no-sync edmi-rag-analyze \
		--index $(abspath $(RAG_INDEX_CSV)) \
		$(ASSET_ARGS) \
		--model $(OLLAMA_ANALYST_MODEL) \
		--output-json $(abspath $(ASSET_ANALYSIS_JSON)) \
		--output-md $(abspath $(ASSET_ANALYSIS_MD))

market-brief:
	$(EDMI_RUN) run --no-sync edmi-rag-brief \
		--index $(abspath $(RAG_INDEX_CSV)) \
		--model $(OLLAMA_ANALYST_MODEL) \
		--output-json $(abspath $(MARKET_BRIEF_JSON)) \
		--output-md $(abspath $(MARKET_BRIEF_MD))

analyze-all: analyze-assets market-brief

rag-query:
	$(EDMI_RUN) run --no-sync edmi-rag-query \
		--index $(abspath $(RAG_INDEX_CSV)) \
		--question "$(QUESTION)"

ragpipe-query:
	$(EDMI_RUN) run --no-sync edmi-ragpipe-query \
		--index-dir $(abspath $(RAGPIPE_INDEX_DIR)) \
		--question "$(QUESTION)"

ragpipe-chat:
	$(EDMI_RUN) run --no-sync edmi-ragpipe-chat \
		--index-dir $(abspath $(RAGPIPE_INDEX_DIR)) \
		--question "$(QUESTION)" \
		--model $(OLLAMA_ANALYST_MODEL) \
		--top-k $(TOP_K)

ragpipe-stream:
	$(EDMI_RUN) run --no-sync edmi-ragpipe-chat \
		--index-dir $(abspath $(RAGPIPE_INDEX_DIR)) \
		--question "$(QUESTION)" \
		--model $(OLLAMA_ANALYST_MODEL) \
		--top-k $(TOP_K) \
		--stream

pipeline: collect-news process-news build-rag ollama-model analyze-all build-ragpipe
	@printf "\nPipeline completed:\n"
	@printf "  raw news:       $(NEWS_CSV_COPY)\n"
	@printf "  processed CSV:  $(PROCESSED_CSV)\n"
	@printf "  RAG index:      $(RAG_INDEX_CSV)\n"
	@printf "  ragpipe index:  $(RAGPIPE_INDEX_DIR)\n"
	@printf "  training JSONL: $(RAG_TRAINING_JSONL)\n"
	@printf "  analysis JSON:  $(ASSET_ANALYSIS_JSON)\n"
	@printf "  analysis MD:    $(ASSET_ANALYSIS_MD)\n"
	@printf "  market brief:   $(MARKET_BRIEF_MD)\n"

pipeline-from-existing-csv: process-news build-rag ollama-model analyze-all build-ragpipe
	@printf "\nPipeline completed from existing CSV:\n"
	@printf "  processed CSV:  $(PROCESSED_CSV)\n"
	@printf "  RAG index:      $(RAG_INDEX_CSV)\n"
	@printf "  ragpipe index:  $(RAGPIPE_INDEX_DIR)\n"
	@printf "  training JSONL: $(RAG_TRAINING_JSONL)\n"
	@printf "  analysis JSON:  $(ASSET_ANALYSIS_JSON)\n"
	@printf "  analysis MD:    $(ASSET_ANALYSIS_MD)\n"
	@printf "  market brief:   $(MARKET_BRIEF_MD)\n"

scheduled-once: collect-news process-news-scheduled build-rag ollama-model analyze-all build-ragpipe
	@printf "\nScheduled iteration completed:\n"
	@printf "  dedup state:    $(DEDUP_STATE_CSV)\n"
	@printf "  processed CSV:  $(PROCESSED_CSV)\n"
	@printf "  RAG index:      $(RAG_INDEX_CSV)\n"
	@printf "  ragpipe index:  $(RAGPIPE_INDEX_DIR)\n"
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
	$(call RM_FILES,$(NEWS_CSV_COPY) $(PROCESSED_CSV) $(DEDUP_STATE_CSV) $(RAG_INDEX_CSV) $(RAG_TRAINING_JSONL) $(OLLAMA_MODELFILE) $(ASSET_ANALYSIS_JSON) $(ASSET_ANALYSIS_MD) $(MARKET_BRIEF_JSON) $(MARKET_BRIEF_MD))
	$(call RM_DIR,$(RAGPIPE_INDEX_DIR))

docker-build:
	docker compose build

docker-up:
	docker compose up -d --build web edmi-api redis postgres ollama ollama-init ollama-ui

docker-pipeline:
	$(DOCKER_ENV_PIPELINE) docker compose --profile pipeline up --build pipeline

docker-pipeline-existing:
	$(DOCKER_ENV_PIPELINE_EXISTING) docker compose --profile pipeline up --build pipeline

docker-schedule:
	$(DOCKER_ENV_SCHEDULE) docker compose --profile pipeline up -d --build pipeline

docker-smoke:
	docker compose --profile smoke run --rm smoke

docker-logs:
	docker compose logs -f --tail=200

docker-down:
	docker compose down
