from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RagDocument:
    doc_id: str
    chunk_id: str
    text: str
    title: str
    source: str
    url: str
    loaded_at: str
    published_at: str
    embedding: list[float]

    def to_json(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "loaded_at": self.loaded_at,
            "published_at": self.published_at,
            "embedding": self.embedding,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> RagDocument:
        return cls(
            doc_id=str(payload.get("doc_id", "")),
            chunk_id=str(payload.get("chunk_id", "")),
            text=str(payload.get("text", "")),
            title=str(payload.get("title", "")),
            source=str(payload.get("source", "")),
            url=str(payload.get("url", "")),
            loaded_at=str(payload.get("loaded_at", "")),
            published_at=str(payload.get("published_at", "")),
            embedding=[float(value) for value in payload.get("embedding", [])],
        )


def configure_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def iter_csv_rows(input_csv: Path) -> Iterable[dict[str, str]]:
    configure_csv_field_limit()
    with input_csv.open("r", encoding="utf-8", newline="") as file:
        yield from csv.DictReader(file)


def row_text(row: dict[str, str]) -> str:
    text = row.get("text", "").strip()
    if text:
        return clean_text(text)
    chunks = row.get("chunks", "").strip()
    if not chunks:
        return ""
    try:
        parsed = json.loads(chunks)
        if isinstance(parsed, list):
            return clean_text("\n".join(str(item) for item in parsed))
    except json.JSONDecodeError:
        pass
    return clean_text(chunks)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def document_id(url: str, title: str, text: str) -> str:
    digest = hashlib.sha256(f"{url}\n{title}\n{text[:2000]}".encode()).hexdigest()
    return digest[:24]


def save_documents(documents: list[RagDocument], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for document in documents:
            file.write(json.dumps(document.to_json(), ensure_ascii=False) + "\n")


def load_documents(path: Path) -> list[RagDocument]:
    if not path.exists():
        return []
    documents: list[RagDocument] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                documents.append(RagDocument.from_json(json.loads(line)))
    return documents
