import csv
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.logging import logger
from app.models import NewsRecord

FIELDNAMES = (
    "source",
    "title",
    "text",
    "url",
    "chunks",
    "loaded_at",
    "published_at",
)


def configure_csv_field_limit() -> int:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            logger.bind(component="storage", field_size_limit=limit).debug(
                "Configured CSV field size limit"
            )
            return limit
        except OverflowError:
            limit //= 10


CSV_FIELD_SIZE_LIMIT = configure_csv_field_limit()


def normalize_value(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url.strip())
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            parsed.query,
            "",
        )
    )


def build_record_key(source: str, url: str, title: str) -> tuple[str, str, str]:
    normalized_source = normalize_value(source)
    normalized_url = normalize_url(url)
    normalized_title = normalize_value(title)
    return (normalized_source, normalized_url, normalized_title)


class CsvRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logger.bind(component="storage", path=str(self.path))
        self.logger.debug("CSV repository initialized")

    def load_all(self) -> list[dict[str, str]]:
        if not self.path.exists():
            self.logger.debug("CSV file does not exist yet")
            return []

        with self.path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            rows = list(reader)
        self.logger.bind(rows=len(rows)).debug("Loaded rows from CSV")
        return rows

    def write_all(self, rows: list[dict[str, str]]) -> None:
        self.logger.bind(rows=len(rows)).debug("Writing rows to CSV")
        with self.path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in FIELDNAMES})
        self.logger.bind(rows=len(rows)).info("CSV write completed")

    def append_news(self, records: list[NewsRecord]) -> int:
        operation_logger = self.logger.bind(operation="append_news", records=len(records))
        existing_rows = self.load_all()
        existing_keys = {
            build_record_key(
                row.get("source", ""),
                row.get("url", ""),
                row.get("title", ""),
            )
            for row in existing_rows
        }

        new_rows: list[dict[str, str]] = []
        skipped_duplicates = 0
        batch_keys: set[tuple[str, str, str]] = set()

        for record in records:
            record_key = build_record_key(record.source, record.url, record.title)
            if record_key in existing_keys or record_key in batch_keys:
                skipped_duplicates += 1
                continue
            batch_keys.add(record_key)
            new_rows.append(record.to_dict())

        if not new_rows:
            operation_logger.bind(skipped_duplicates=skipped_duplicates).info(
                "No new rows to append"
            )
            return 0

        merged = existing_rows + new_rows
        self.write_all(merged)
        operation_logger.bind(
            inserted=len(new_rows),
            skipped_duplicates=skipped_duplicates,
            rows_total=len(merged),
        ).info("Appended new rows")
        return len(new_rows)

    def replace_source(self, source: str, records: list[NewsRecord]) -> int:
        operation_logger = self.logger.bind(
            operation="replace_source",
            source=source,
            records=len(records),
        )
        existing_rows = self.load_all()
        filtered_rows = [row for row in existing_rows if row.get("source") != source]
        unique_records: list[dict[str, str]] = []
        batch_keys: set[tuple[str, str, str]] = set()

        for record in records:
            record_key = build_record_key(record.source, record.url, record.title)
            if record_key in batch_keys:
                continue
            batch_keys.add(record_key)
            unique_records.append(record.to_dict())

        filtered_rows.extend(unique_records)
        self.write_all(filtered_rows)
        operation_logger.bind(
            rows_total=len(filtered_rows), unique_records=len(unique_records)
        ).info("Source rows replaced")
        return len(unique_records)
