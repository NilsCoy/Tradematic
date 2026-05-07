# News Aggregator

`FastAPI`-приложение для сбора новостей из открытых источников и обновления курсов ЦБ РФ.

## Что делает

- собирает новости из множества русских и иностранных источников
- старается извлекать полный текст статьи, а не анонс
- отбрасывает короткие материалы меньше `300` слов
- добавляет `loaded_at` и по возможности `published_at`
- разбивает текст на чанки и сохраняет в `CSV`
- обновляет расширенный набор валют ЦБ РФ
- поддерживает `SSE`-стриминг прогресса сбора
- использует перевод в русский для части англоязычных источников

## Установка и запуск

Проект использует `uv`, а не `requirements.txt`.

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Можно запускать и через `Makefile`.

## Команды Makefile

```bash
make install
make install-dev
make run
make format
make lint
make check
```

Описание команд:

- `make install` - установить зависимости через `uv`
- `make install-dev` - установить зависимости вместе с dev-инструментами
- `make run` - запустить приложение через `uvicorn`
- `make format` - форматирование проекта через `ruff format`
- `make lint` - проверка проекта через `ruff check`
- `make check` - автоисправления `ruff` и повторное форматирование

## Ручки

- `GET /health` - проверка сервиса
- `POST /collect` - один проход сбора
- `GET /collect/stream` - потоковый сбор в формате `SSE`
- `GET /dataset` - превью сохраненных строк из `CSV`

## Формат CSV

Файл создается автоматически: `data/news_dataset.csv`

Колонки:

- `source`
- `title`
- `text`
- `url`
- `chunks`
- `loaded_at`
- `published_at`

## Разработка

Проверка качества кода:

```bash
make format
make lint
```

или одной командой:

```bash
make check
```
