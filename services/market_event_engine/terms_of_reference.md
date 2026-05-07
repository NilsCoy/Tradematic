# 📄 Техническое задание

## Проект: **EventDrivenMarket Intelligence (EDMI)**

---

# 1. Цель системы

Разработка асинхронного сервиса, который:

* принимает поток новостей (CSV/stream)
* агрегирует их в события
* извлекает сущности (NER)
* классифицирует события (LLM)
* определяет релевантность активам пользователя (LLM)
* оценивает влияние событий на рынок (на основе рыночных данных)
* предоставляет API для анализа активов и портфелей

---

# 2. Общая архитектура

## Тип:

* асинхронный сервис
* event-driven pipeline

---

## Компоненты:

```text
Ingestion → Queue → Workers → Pipeline → Storage → API
```

---

## Слои:

1. **Ingestion Layer**
2. **Application Layer (Orchestrator)**
3. **Domain Services**
4. **Infrastructure Layer (DB, Redis, LLM)**
5. **API Layer**

---

# 3. Технологический стек

## Язык

* Python **3.13**

---

## Backend

* FastAPI
* Pydantic v2
* Uvicorn + uvloop

---

## Асинхронность

* asyncio
* httpx

---

## Очередь задач

* ARQ (Redis-based async queue)

---

## Хранилище

* PostgreSQL 16
* pgvector

---

## Кэш

* Redis

---

## ML / NLP

* sentence-transformers (multilingual)
* scikit-learn (DBSCAN)
* Natasha (RU NER)
* spaCy (fallback)

---

## LLM

* Ollama
* модель: `llama3.1`

---

## Контейнеризация

* Docker
* docker-compose

---

# 4. Формат входных данных

## Источник:

CSV-файл (стриминг)

---

## Формат:

```csv
source,title,text,url,chunks,loaded_at,published_at
```

---

## Требования:

* чтение построчно (streaming)
* поддержка больших файлов (>1GB)
* отсутствие загрузки файла в память

---

# 5. Ingestion Layer

## Функциональность:

1. Построчное чтение CSV
2. Валидация данных
3. Очистка текста
4. Фильтрация мусора
5. Дедупликация
6. Отправка в очередь

---

## Реализация:

* генераторы (`yield`)
* batch обработка (50–100 записей)

---

## Дедупликация:

* SHA-256 от текста
* Redis (SET/EXISTS)

---

## DTO:

```python
class RawNews(BaseModel):
    source: str
    title: str
    text: str
    url: str
    published_at: datetime
```

---

# 6. Очередь задач

## ARQ

---

## Требования:

* асинхронная обработка
* retry механизм
* ограничение параллелизма

---

## Задачи:

* `process_news`
* `process_batch`

---

# 7. Pipeline обработки

## Оркестратор

### Название:

`NewsProcessingPipeline`

---

## Функция:

```python
async def process(news: RawNews) -> ProcessedEvent
```

---

## Этапы:

---

### 7.1 Preprocessing

* очистка текста
* нормализация
* удаление HTML

---

### 7.2 Embedding

## Технология:

* sentence-transformers

---

## Модель:

* multilingual-e5-base (предпочтительно)

---

## Выход:

```python
embedding: list[float]
```

---

### 7.3 Deduplication (semantic)

* cosine similarity
* threshold: 0.85

---

### 7.4 Clustering

## Метод:

* DBSCAN

---

## Параметры:

* eps = 0.3
* metric = cosine

---

## Выход:

* event_id

---

### 7.5 NER

## Технологии:

* Natasha (основной)
* spaCy (fallback)

---

## Извлекаемые сущности:

* компании
* товары (commodities)
* макроэкономические факторы

---

## Выход:

```json
{
  "companies": [],
  "commodities": [],
  "macro": []
}
```

---

### 7.6 Event Classification (LLM)

## Вход:

* текст события
* сущности

---

## Выход:

```json
{
  "event_type": "...",
  "confidence": 0.0-1.0
}
```

---

## Типы событий:

* earnings
* product_launch
* regulation
* macro
* geopolitics
* supply_chain

---

---

### 7.7 Relevance Classification (LLM)

## Вход:

* событие
* сущности
* актив

---

## Выход:

```json
{
  "level": "...",
  "confidence": 0.0-1.0,
  "explanation": "..."
}
```

---

## Уровни:

* direct
* industry
* supply_chain
* macro
* global
* noise

---

---

### 7.8 Market Data Integration

## Источник:

* API T-bank

---

## Расчёт:

```python
delta = (price_t+Δ - price_t) / price_t
```

---

## Таймфреймы:

* 1 час
* 1 день

---

---

### 7.9 Impact Calculation

## Формула:

```python
impact = delta * relevance_weight
```

---

## Вес:

```python
{
  "direct": 1.0,
  "industry": 0.7,
  "supply_chain": 0.5,
  "macro": 0.3,
  "global": 0.2,
  "noise": 0.0
}
```

---

---

### 7.10 Explanation (LLM)

## Вход:

* событие
* delta
* relevance
* entities

---

## Выход:

* текстовое объяснение

---

# 8. Хранилище данных

## PostgreSQL + pgvector

---

## Таблицы:

### news

* id
* text
* embedding

---

### events

* id
* event_type
* centroid_embedding

---

### event_news

* event_id
* news_id

---

### event_asset_relation

* event_id
* asset
* level
* confidence
* explanation

---

### event_market_effect

* event_id
* delta_1h
* delta_1d

---

# 9. API

## FastAPI

---

## Эндпоинты:

```http
GET /events/{asset}
GET /impact/{asset}
GET /portfolio/{id}/analysis
```

---

# 10. LLM сервис

## Требования:

* обёртка над Ollama
* retry
* timeout
* JSON validation
* кеширование (Redis)

---

# 11. Конфигурация

## Pydantic Settings

* DB URL
* Redis URL
* Ollama URL
* model name

---

# 12. Docker

## Требования:

* docker-compose
* CPU-only режим
* GPU (опционально)

---

## Сервисы:

* api
* worker
* postgres
* redis
* ollama

---

# 13. Нефункциональные требования

## Производительность:

* обработка ≥ 1000 новостей/час

---

## Масштабируемость:

* горизонтальное масштабирование воркеров

---

## Надёжность:

* retry задач
* идемпотентность

---

## Логирование:

* structured logging (JSON)

---

# 14. Ограничения

* LLM не используется для расчёта цен
* система не даёт инвестиционных рекомендаций
* обработка только текстовых новостей

---

# 15. Результат работы системы

Для каждого актива:

* список событий
* тип событий
* уровень влияния
* численное влияние (impact)
* текстовое объяснение

---

# 16. Критерии готовности (Definition of Done)

✔ ingestion работает стримингом
✔ pipeline обрабатывает новости
✔ LLM интегрирован
✔ события формируются
✔ влияние считается
✔ API отдаёт результат
✔ система запускается через docker-compose

---

# Итог

✔ полноценный AI pipeline
✔ асинхронную архитектуру
✔ data engineering + ML + LLM
✔ объяснимую систему


Параллельно тебе для сведения. Новостной аггрегатор находится по пути: /Users/murzilka/Desktop/Dev/news_aggregator; Хранение csv находится там же папке /data, но он большой не читай его

Сам проект с алгоритмами и получением банковской информации в /Users/murzilka/Desktop/Dev/Tradematic;