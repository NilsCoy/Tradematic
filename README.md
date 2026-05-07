# Tradematic

## Монолитный новостной pipeline

В репозиторий встроены:

- `services/news_aggregator` - сборщик новостей.
- `services/market_event_engine` - EDMI processing: dedup, embeddings, NER, Ollama classification, relevance, Tradematic price delta.
- `main/scripts/datasets` - единое CSV-хранилище Tradematic.

Полный сценарий одной командой:

```bash
make install-services
make pipeline ASSETS="SBER GAZP" LIMIT=20
```

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
```

`rag_training.jsonl` - это выгрузка обучающих примеров из CSV. Локальная Ollama не дообучает веса модели этим файлом напрямую, поэтому рабочая реализация сделана как RAG: новости индексируются, релевантный контекст подается в локальную модель `tradematic-analyst`, а результат сохраняется как анализ по каждому активу.

Если CSV новостей уже собран и нужно только переобработать:

```bash
make pipeline-from-existing-csv ASSETS="SBER GAZP" LIMIT=20
```

Проверить RAG-поиск:

```bash
make rag-query QUESTION="Какие события важны для SBER?"
```

Перед первым запуском убедитесь, что локально доступна Ollama:

```bash
make ollama-check
```

Основная команда для ежедневного запуска:

```bash
make pipeline ASSETS="SBER" LIMIT=20
```

На выходе главный отчет лежит в `main/scripts/datasets/asset_analysis.md`.

## Использование Makefile

Проект использует Makefile для упрощения типовых задач разработки на Django с использованием менеджера пакетов uv.

## Команды

> **make install**

Устанавливает все зависимости из lock-файла с помощью uv sync.

> **make run**

Запускает Django-сервер разработки на 0.0.0.0:8000.

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
