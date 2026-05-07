# Tradematic

## Монолитный новостной pipeline

В репозиторий встроены:

- `services/news_aggregator` - сборщик новостей.
- `services/market_event_engine` - EDMI processing: dedup, embeddings, NER, Ollama classification, relevance, Tradematic price delta.
- `main/scripts/datasets` - единое CSV-хранилище Tradematic.

Полный сценарий одной командой:

```bash
make install
make pipeline LIMIT=20
```

`make install` создает один общий корневой `.venv` для всего монолита Tradematic: Django-приложения, `services/news_aggregator` и `services/market_event_engine`. Сервисные пакеты подключены через группу зависимостей `services` в `pyproject.toml` как editable path-зависимости, поэтому отдельные `.venv` внутри сервисов больше не нужны.

Для локального запуска интерфейса:

```bash
make install
make migrate
make run
```

После запуска UI доступен на `http://127.0.0.1:8001/`.

Если нужен контролируемый universe активов, используйте файл, чтобы не упереться в длину командной строки:

```bash
make pipeline ASSETS_FILE=main/scripts/datasets/assets.txt LIMIT=20
```

Если файл `main/scripts/datasets/assets.txt` существует, Makefile подхватит его автоматически даже без `ASSETS_FILE=...`.

Файл активов может содержать тикеры по одному на строку, через пробелы или запятые:

```text
TICKER_A
TICKER_B TICKER_C
TICKER_D, TICKER_E
# комментарии игнорируются
```

Важно: NER не является источником списка активов. Он извлекает сущности из новости, но не решает, какие тикеры анализировать. EDMI processing обрабатывает каждую новость один раз как общий новостной фон `MARKET`, а список активов используется на финальном RAG-анализе. Если явный список активов не передан и `main/scripts/datasets/assets.txt` отсутствует, `asset_analysis.*` тоже строится только для общего среза `MARKET`, чтобы туда не попадали названия источников вроде Reuters/RIA.RU.

Что делает `make pipeline`:

```text
news_aggregator collect
  -> main/scripts/datasets/news_dataset.csv
  -> EDMI processing через Ollama + Tradematic price datasets
  -> main/scripts/datasets/processed_events.csv
  -> RAG index
  -> main/scripts/datasets/rag_index.csv
  -> main/scripts/datasets/rag_training.jsonl
  -> Ollama model wrapper tradematic-analyst
  -> main/scripts/datasets/asset_analysis.json
  -> main/scripts/datasets/asset_analysis.md
  -> main/scripts/datasets/market_brief.json
  -> main/scripts/datasets/market_brief.md
```

`rag_training.jsonl` - это выгрузка обучающих примеров из CSV. Локальная Ollama не дообучает веса модели этим файлом напрямую, поэтому рабочая реализация сделана как RAG: новости индексируются, релевантный контекст подается в локальную модель `tradematic-analyst`, а результат сохраняется как анализ по каждому активу.

## Файлы результата pipeline

После `make pipeline` основные артефакты лежат в `main/scripts/datasets`.

| Файл | За что отвечает |
| --- | --- |
| `services/news_aggregator/data/news_dataset.csv` | Рабочий CSV самого парсера новостей. Сюда сборщик пишет найденные новости и валютные данные до EDMI-обработки. |
| `main/scripts/datasets/news_dataset.csv` | Копия сырого CSV внутри общего хранилища Tradematic. Удобная входная точка для последующих шагов и ручной проверки результата сбора. |
| `main/scripts/datasets/processed_events.csv` | Главный обработанный датасет событий. Здесь уже есть dedup, NER-сущности и классификация события. Колонка `asset` остается общим срезом `MARKET`, чтобы размер датасета не рос как `количество новостей × количество активов`. |
| `main/scripts/datasets/processed_state.csv` | Persistent state дедупликации для `make schedule` и `make process-news-scheduled`. Нужен, чтобы повторные новости не уходили заново в NER/LLM между итерациями расписания. |
| `main/scripts/datasets/rag_index.csv` | CSV-backed RAG index. Из него выбирается релевантный контекст для вопроса или анализа конкретного актива. |
| `main/scripts/datasets/rag_training.jsonl` | JSONL-представление обработанных событий как обучающих/контекстных примеров. В текущей реализации используется как подготовленный корпус для RAG, а не как fine-tune весов Ollama. |
| `main/scripts/datasets/Modelfile.tradematic-analyst` | Modelfile для создания локальной Ollama-обертки `tradematic-analyst` поверх базовой модели, по умолчанию `llama3.1`. |
| `main/scripts/datasets/asset_analysis.json` | Машиночитаемый итоговый анализ по активам из `ASSETS`, `ASSETS_FILE` или автоматического `main/scripts/datasets/assets.txt`. Каждый актив оценивается по всему новостному фону из RAG. |
| `main/scripts/datasets/asset_analysis.md` | Человекочитаемый итоговый отчет по активам. Это основной файл, который стоит открывать после завершения pipeline. |
| `main/scripts/datasets/market_brief.json` | Машиночитаемая сводка всего новостного фона по категориям: общий обзор, макроэкономика, геополитика, корпоративные события, сырье/цепочки поставок и risk watch. Генерируется LLM параллельно с анализом активов. |
| `main/scripts/datasets/market_brief.md` | Человекочитаемый аналитический brief для ручной проверки новостного фона. Удобно открывать вместе с `asset_analysis.md`. |

Файлы `daily_data.csv`, `hourly_data.csv`, `weekly_data.csv`, `monthly_data.csv` и `stock_data.csv`, если лежат в `main/scripts/datasets`, относятся к рыночным данным Tradematic. Pipeline использует их как источник ценового контекста, но не пересоздает их при сборе новостей.

Если CSV новостей уже собран и нужно только переобработать:

```bash
make pipeline-from-existing-csv LIMIT=20
```

Для больших списков:

```bash
make pipeline-from-existing-csv ASSETS_FILE=main/scripts/datasets/assets.txt LIMIT=20
```

Проверить RAG-поиск:

```bash
make rag-query QUESTION="Какие события важны для рынка?"
```

Перед первым запуском убедитесь, что локально доступна Ollama:

```bash
make ollama-check
```

Основная команда для ежедневного запуска:

```bash
make pipeline LIMIT=20
```

На выходе главный отчет лежит в `main/scripts/datasets/asset_analysis.md`.
Общая аналитическая сводка по категориям лежит в `main/scripts/datasets/market_brief.md`.

## Запуск по расписанию

Для постоянной работы pipeline:

```bash
make schedule ASSETS_FILE=main/scripts/datasets/assets.txt LIMIT=20 INTERVAL_SECONDS=900
```

Каждая итерация делает полный цикл: сбор новостей, persistent dedup, EDMI processing с NER/Ollama/price delta, обновление CSV, пересборку RAG и выпуск анализа по активам.

Для дедупликации между итерациями используется `main/scripts/datasets/processed_state.csv`. В нем хранятся хэши и embeddings уже обработанных новостей, поэтому повторные новости не отправляются заново в NER/LLM даже если снова встретились позже.

Остановить расписание можно обычным `Ctrl+C`.

## Использование Makefile

Проект использует Makefile для упрощения типовых задач разработки на Django с использованием менеджера пакетов uv.

## Команды

> **make install**

Устанавливает все зависимости из lock-файла в общий корневой `.venv`: Django, dev-инструменты и сервисную группу `services`.

> **make run**

Запускает Django-сервер разработки на `127.0.0.1:8001`.

> **make migrate**

Применяет все доступные миграции базы данных.

> **make makemigrations**

Создает новые файлы миграций для изменений в моделях.

> **make shell**

Открывает интерактивную оболочку Django.

> **make collect-static**

Собирает все статические файлы в директорию static root без подтверждения.

> **make superuser**

Создает администратора Django.

> **make test**

Запускает тесты проекта.

> **make format**

Автоматически форматирует и исправляет код с помощью Ruff.

> **make lint**

Проверяет код на ошибки и несоответствия стилю с помощью Ruff.

> **make uv-lock**

Пересоздает lock-файл зависимостей uv.lock.

> **make uv-update**

Обновляет все зависимости до последних совместимых версий.
