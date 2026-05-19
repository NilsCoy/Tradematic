# Как тестировать пайплайн

Документ описывает быстрые и полные проверки связки:

```text
парсер новостей → EDMI processing → RAG/RAGPipe → Ollama → Tradematic chat
```

## 1. Быстрая проверка кода

Перед запуском можно посмотреть, какую платформенную конфигурацию выбрал Makefile:

```bash
make config
```

Команда показывает ОС, выбранный Python, путь к venv и директорию датасетов.

```bash
uv run --no-sync ruff check services/market_event_engine services/ragpipe main invest
uv run --no-sync python manage.py check
```

Эти команды проверяют Python-код, Django-конфигурацию, роуты и базовые импорты.

## 2. Регулируемые параметры Makefile

Все параметры можно передавать прямо в команду:

```bash
make pipeline LIMIT=20 RAGPIPE_MAX_DOCUMENTS=80
make ragpipe-chat TOP_K=1 RAGPIPE_CHAT_CONTEXT_CHARS=500 QUESTION="Что по рынку?"
```

Основные параметры:

| Параметр | Значение по умолчанию | Где используется | Что регулирует |
|---|---:|---|---|
| `TRADER_PYTHON` | Windows: `3.10`, macOS/Linux: `python3.10` | `make install` | Какой Python использует `uv sync`. Можно указать путь к конкретному Python 3.10. |
| `UV` | `uv` | все uv-команды | Имя или путь к исполняемому `uv`. |
| `LIMIT` | `20` | `process-news`, `pipeline`, Docker pipeline | Сколько новостей обработать за один прогон EDMI. Для быстрой проверки ставить `5`; для нормального прогона увеличивать. |
| `RAGPIPE_MAX_DOCUMENTS` | `80` | `build-ragpipe` | Максимум чанков/документов на один источник при построении RAGPipe-индекса. Чем больше, тем шире база знаний и медленнее build/chat. |
| `ASSETS` | пусто | `analyze-assets`, `pipeline` | Список активов прямо в команде, например `ASSETS="SBER GAZP"`. |
| `ASSETS_FILE` | авто: `main/scripts/datasets/assets.txt`, если существует | `analyze-assets`, `pipeline` | Файл со списком активов. Удобнее для большого количества тикеров. |
| `INTERVAL_SECONDS` | `900` | `schedule`, `docker-schedule` | Интервал между scheduled-прогонами пайплайна. |
| `QUESTION` | `Какие события сильнее всего влияют на рынок?` | `rag-query`, `ragpipe-query`, `ragpipe-chat`, `ragpipe-stream` | Вопрос для CLI-проверки RAG/чата. |
| `TOP_K` | `4` | `ragpipe-chat`, `ragpipe-stream` | Сколько найденных RAG-фрагментов передавать в LLM. Меньше = быстрее и меньше риск шума; больше = шире контекст. |
| `RAGPIPE_CHAT_TIMEOUT` | `600` | `ragpipe-chat`, `ragpipe-stream`, `run-edmi` | Таймаут ожидания ответа Ollama для RAGPipe-чата. |
| `RAGPIPE_CHAT_CONTEXT_CHARS` | `900` | `ragpipe-chat`, `ragpipe-stream`, `run-edmi` | Максимум символов текста из каждого найденного chunk, который попадёт в prompt. |
| `RAGPIPE_CHAT_NUM_PREDICT` | `384` | `ragpipe-chat`, `ragpipe-stream`, `run-edmi` | Максимальная длина ответа Ollama в токенах. |
| `OLLAMA_BASE_MODEL` | `llama3.1` | `ollama-model` | Базовая модель для Modelfile аналитика. |
| `OLLAMA_ANALYST_MODEL` | `tradematic-analyst` | `ollama-model`, анализ, чат | Имя локальной Ollama-модели-аналитика. |
| `OLLAMA_URL` | `http://localhost:11434` или `EDMI_OLLAMA_URL` | `ollama-model` | URL локальной/контейнерной Ollama. |

Практические режимы:

Быстрая проверка:

```bash
make pipeline LIMIT=5 RAGPIPE_MAX_DOCUMENTS=20
make ragpipe-chat TOP_K=1 RAGPIPE_CHAT_CONTEXT_CHARS=500 RAGPIPE_CHAT_NUM_PREDICT=160 QUESTION="Что по рынку?"
```

Более полный локальный прогон:

```bash
make pipeline LIMIT=50 RAGPIPE_MAX_DOCUMENTS=200
```

Запуск только сайта и чата, если RAG уже собран:

```bash
make run-edmi RAGPIPE_CHAT_CONTEXT_CHARS=500 RAGPIPE_CHAT_NUM_PREDICT=160
make run
```

Scheduled-режим:

```bash
make schedule LIMIT=20 INTERVAL_SECONDS=900
```

## 3. Быстрый локальный пайплайн без Docker

Если зависимости уже установлены и Ollama запущена локально:

```bash
make pipeline LIMIT=5 RAGPIPE_MAX_DOCUMENTS=20
```

Для запуска без повторного сбора новостей, на уже существующем CSV:

```bash
make pipeline-from-existing-csv LIMIT=5 RAGPIPE_MAX_DOCUMENTS=20
```

После успешного запуска должны появиться или обновиться файлы:

```text
main/scripts/datasets/news_dataset.csv
main/scripts/datasets/processed_events.csv
main/scripts/datasets/rag_index.csv
main/scripts/datasets/rag_training.jsonl
main/scripts/datasets/asset_analysis.json
main/scripts/datasets/asset_analysis.md
main/scripts/datasets/market_brief.json
main/scripts/datasets/market_brief.md
main/scripts/datasets/ragpipe/
```

## 4. Полная проверка через Docker

Поднять основные сервисы:

```bash
make docker-up
```

Проверить состояние контейнеров:

```bash
docker compose ps
```

Запустить один полный пайплайн:

```bash
make docker-pipeline LIMIT=5 RAGPIPE_MAX_DOCUMENTS=20
```

Для более репрезентативной проверки:

```bash
make docker-pipeline LIMIT=20 RAGPIPE_MAX_DOCUMENTS=80
```

## 5. Смотреть логи

Логи всех сервисов:

```bash
docker compose logs -f
```

Логи пайплайна:

```bash
docker compose --profile pipeline logs -f pipeline
```

Логи EDMI API:

```bash
docker compose logs -f edmi-api
```

Логи Tradematic UI:

```bash
docker compose logs -f web
```

Логи Ollama:

```bash
docker compose logs -f ollama
```

В `edmi-export-events` добавлены stage-логи:

- старт обработки;
- загруженное состояние дедупликации;
- получение batch;
- прогресс каждые N строк;
- количество accepted / duplicates / state_duplicates;
- финальный итог.

В `RAGPipe build` добавлены stage-логи:

- старт сборки индекса;
- начало и конец обработки каждого CSV;
- начало и конец обработки каждого text input;
- запись documents JSONL;
- запись BM25;
- запись FAISS;
- запись Chroma;
- финальный итог.

## 6. Проверка RAGPipe вопросом

После успешного пайплайна можно проверить retrieval и ответ Ollama:

```bash
make ragpipe-query QUESTION="Какие новости сейчас важны для рынка?"
```

И полноценный ответ через Ollama:

```bash
make ragpipe-chat QUESTION="Дай краткую рыночную сводку по последним событиям"
```

Стриминг:

```bash
make ragpipe-stream QUESTION="Какие события сильнее всего влияют на активы?"
```

## 7. Проверка UI-чата

После запуска Docker:

```text
http://localhost:8001/
```

Дальше:

1. авторизоваться;
2. перейти в панель;
3. увидеть кнопку `AI чат`;
4. открыть чат;
5. задать вопрос по рынку или новостям.

Чат доступен только после авторизации:

- `/panel/` защищён;
- `/chat/` защищён;
- `/api/ragpipe/chat/` защищён и принимает только POST.

## 8. Проверка Open WebUI

Open WebUI доступен по адресу:

```text
http://localhost:3000/
```

Он подключён к:

```text
Ollama: http://ollama:11434
EDMI OpenAI-compatible API: http://edmi-api:8000/v1
```

## 9. Проверка healthcheck

Smoke-проверка:

```bash
make docker-smoke
```

Она должна подтвердить, что основные HTTP-сервисы отвечают и критичные артефакты доступны.

## 10. Как понять, что всё прошло успешно

Успешный пайплайн заканчивается блоком:

```text
Pipeline completed:
  raw news:       main/scripts/datasets/news_dataset.csv
  processed CSV:  main/scripts/datasets/processed_events.csv
  RAG index:      main/scripts/datasets/rag_index.csv
  ragpipe index:  main/scripts/datasets/ragpipe
  training JSONL: main/scripts/datasets/rag_training.jsonl
  analysis JSON:  main/scripts/datasets/asset_analysis.json
  analysis MD:    main/scripts/datasets/asset_analysis.md
  market brief:   main/scripts/datasets/market_brief.md
```

После этого можно тестировать чат через Tradematic UI или через `make ragpipe-chat`.
