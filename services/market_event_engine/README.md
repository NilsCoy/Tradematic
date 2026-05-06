# EventDrivenMarket Intelligence

Асинхронный сервис для потоковой загрузки новостей, агрегации в события, извлечения сущностей, LLM-классификации, оценки релевантности активам и расчета рыночного влияния.

## Быстрый старт

```bash
uv python install 3.13
uv sync --all-extras --dev
uv run uvicorn edmi.api.main:create_app --factory --reload
```

То же через Makefile:

```bash
make python
make sync
make api
```

Для инфраструктуры:

```bash
docker compose up --build
```

или:

```bash
make docker-up
```

Docker-образ тоже собирается через `uv` и использует `uv.lock`.

## Ingestion CSV

Ожидаемые колонки:

```csv
source,title,text,url,chunks,loaded_at,published_at
```

Запуск потоковой загрузки:

```bash
uv run edmi-ingest path/to/news.csv
```

Через Makefile:

```bash
make ingest CSV=path/to/news.csv ASSET=AAPL
```

## API

- `GET /events/{asset}`
- `GET /impact/{asset}`
- `GET /portfolio/{id}/analysis`
- `POST /ingest/news`
- `POST /ingest/csv`

## Внешние сервисы

Сервис работает без ML/LLM/Redis/PostgreSQL в fallback-режиме, чтобы локальная разработка стартовала сразу. Для production-подключения задайте переменные из `.env.example`.

## Основные команды

- `make sync` - установка зависимостей через `uv`
- `make test` - запуск тестов
- `make compile` - синтаксическая проверка
- `make api` - запуск FastAPI
- `make worker` - запуск ARQ worker
- `make parser-collect` - один проход соседнего `news_aggregator`
- `make ingest-parser ASSET=SBER LIMIT=5` - загрузка свежих строк parser CSV в EDMI
- `make pipeline ASSET=SBER LIMIT=5 COLLECT=1` - parser collect + EDMI processing через API
- `make pipeline-local ASSET=SBER LIMIT=5 COLLECT=1` - прямой CLI pipeline
- `make docker-up` - запуск Redis/PostgreSQL/API/worker в Docker Compose

## Готовый Parser → EDMI Pipeline

1. Собрать новости соседним парсером:

```bash
make parser-collect
```

Парсер пишет CSV в:

```text
../news_aggregator/data/news_dataset.csv
```

2. Запустить EDMI API:

```bash
make api
```

3. Запустить полный pipeline через EDMI API:

```bash
make pipeline ASSET=SBER LIMIT=5 COLLECT=1
```

Если parser уже запускался и нужно только обработать текущий CSV:

```bash
make pipeline ASSET=SBER LIMIT=5
```

4. Посмотреть результаты и покрытие Tradematic данных:

```bash
curl http://127.0.0.1:8000/events/SBER
curl http://127.0.0.1:8000/impact/SBER
curl http://127.0.0.1:8000/market-data/SBER/coverage
```

`/ingest/news-aggregator` по умолчанию читает самые свежие строки CSV. Общий `/ingest/csv` сохраняет streaming-порядок файла.
