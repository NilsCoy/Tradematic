import csv
import sys
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from edmi.domain.models import RawNews
from edmi.ingestion.cleaning import clean_text, is_noise


REQUIRED_COLUMNS = {"source", "title", "text", "url", "published_at"}


def configure_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def iter_raw_news(path: str | Path, newest_first: bool = False) -> Iterator[RawNews]:
    configure_csv_field_limit()
    with Path(path).open("r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            missing = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

        rows: Iterator[dict[str, str]]
        if newest_first:
            rows = iter(
                sorted(
                    reader,
                    key=lambda row: row.get("published_at", "") or row.get("loaded_at", ""),
                    reverse=True,
                )
            )
        else:
            rows = reader

        for row in rows:
            yield from _row_to_raw_news(row)


def iter_batches(items: Iterator[RawNews], batch_size: int) -> Iterator[list[RawNews]]:
    batch: list[RawNews] = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


async def async_iter_batches(path: str | Path, batch_size: int) -> AsyncIterator[list[RawNews]]:
    for batch in iter_batches(iter_raw_news(path), batch_size):
        yield batch


def _row_to_raw_news(row: dict[str, str]) -> Iterator[RawNews]:
    title = clean_text(row.get("title", ""))
    text = clean_text(row.get("text") or row.get("chunks", ""))
    if is_noise(title, text):
        return
    try:
        yield RawNews(
            source=clean_text(row.get("source", "")),
            title=title,
            text=text,
            url=row.get("url", ""),
            published_at=_parse_datetime(row.get("published_at", "") or row.get("loaded_at", "")),
        )
    except (ValidationError, ValueError):
        return


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)
