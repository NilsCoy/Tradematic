from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from edmi.application.factory import make_pipeline
from edmi.application.pipeline import DuplicateNewsError
from edmi.config import get_settings
from edmi.domain.models import ProcessedEvent
from edmi.ingestion.cleaning import clean_text
from edmi.ingestion.csv_stream import iter_batches, iter_raw_news
from edmi.infrastructure.dedup import text_hash
from edmi.services.embedding import EmbeddingService
from edmi.services.vector import cosine_similarity


MARKET_ASSET = "MARKET"

FIELDNAMES = (
    "event_id",
    "news_id",
    "asset",
    "source",
    "title",
    "url",
    "published_at",
    "event_type",
    "event_confidence",
    "relevance_level",
    "relevance_confidence",
    "relevance_explanation",
    "delta_1h",
    "delta_1d",
    "impact_1h",
    "impact_1d",
    "impact_explanation",
    "entities_json",
    "text",
)

STATE_FIELDNAMES = (
    "text_hash",
    "embedding_json",
    "source",
    "title",
    "url",
    "published_at",
)


async def export_processed_events(
    input_csv: Path,
    output_csv: Path,
    assets: list[str],
    limit: int | None,
    newest_first: bool,
    state_csv: Path | None = None,
    append: bool = False,
) -> dict[str, int | str]:
    settings = get_settings()
    pipeline = await make_pipeline()
    embedding_service = EmbeddingService(settings)
    state = _load_state(state_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    accepted = 0
    duplicates = 0
    processed = 0
    state_duplicates = 0
    mode = "a" if append and output_csv.exists() else "w"
    with output_csv.open(mode, encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        if mode == "w":
            writer.writeheader()
        for batch in iter_batches(
            iter_raw_news(input_csv, newest_first=newest_first),
            settings.batch_size,
        ):
            for news in batch:
                if limit is not None and processed >= limit:
                    _save_state(state_csv, state)
                    return _summary(input_csv, output_csv, accepted, duplicates, state_duplicates, processed)
                cleaned_title = clean_text(news.title)
                cleaned_text = clean_text(news.text)
                digest = text_hash(cleaned_text)
                if digest in state["hashes"]:
                    state_duplicates += 1
                    processed += 1
                    continue

                embedding = await embedding_service.embed(f"{cleaned_title}\n{cleaned_text}")
                if _is_semantic_duplicate(embedding, state["embeddings"], settings.semantic_dup_threshold):
                    state["hashes"].add(digest)
                    state["rows"].append(_state_row_from_news(digest, embedding, news))
                    state_duplicates += 1
                    processed += 1
                    continue

                try:
                    event = await pipeline.process(news, assets)
                    accepted += 1
                    for row in _event_rows(event, assets):
                        writer.writerow(row)
                    state["hashes"].add(digest)
                    state["rows"].append(_state_row(event))
                    state["embeddings"].append(event.embedding)
                except DuplicateNewsError:
                    state["hashes"].add(digest)
                    state["rows"].append(_state_row_from_news(digest, embedding, news))
                    duplicates += 1
                finally:
                    processed += 1

    _save_state(state_csv, state)
    return _summary(input_csv, output_csv, accepted, duplicates, state_duplicates, processed)


def _event_rows(event: ProcessedEvent, assets: list[str]) -> list[dict]:
    rows = []
    normalized_assets = _normalize_assets(assets) or [MARKET_ASSET]
    for asset in normalized_assets:
        relation = event.asset_relations.get(asset)
        effect = event.market_effects.get(asset)
        rows.append(
            {
                "event_id": str(event.id),
                "news_id": str(event.news_id),
                "asset": asset,
                "source": event.raw_news.source,
                "title": event.raw_news.title,
                "url": str(event.raw_news.url),
                "published_at": event.raw_news.published_at.isoformat(),
                "event_type": event.classification.event_type.value,
                "event_confidence": event.classification.confidence,
                "relevance_level": relation.level.value if relation else "",
                "relevance_confidence": relation.confidence if relation else "",
                "relevance_explanation": relation.explanation if relation else "",
                "delta_1h": effect.delta_1h if effect else "",
                "delta_1d": effect.delta_1d if effect else "",
                "impact_1h": effect.impact_1h if effect else "",
                "impact_1d": effect.impact_1d if effect else "",
                "impact_explanation": effect.explanation if effect else "",
                "entities_json": event.entities.model_dump_json(),
                "text": event.raw_news.text,
            }
        )
    return rows


def _normalize_assets(assets: list[str]) -> list[str]:
    normalized = []
    for asset in assets:
        clean = " ".join(asset.strip().split()).upper()
        if clean:
            normalized.append(clean)
    return list(dict.fromkeys(normalized))


def _summary(
    input_csv: Path,
    output_csv: Path,
    accepted: int,
    duplicates: int,
    state_duplicates: int,
    processed: int,
) -> dict[str, int | str]:
    return {
        "input_csv": str(input_csv),
        "output_csv": str(output_csv),
        "accepted": accepted,
        "duplicates": duplicates,
        "state_duplicates": state_duplicates,
        "processed": processed,
    }


async def _run(args: argparse.Namespace) -> None:
    assets = _load_assets(args.asset, Path(args.assets_file) if args.assets_file else None)
    summary = await export_processed_events(
        input_csv=Path(args.input),
        output_csv=Path(args.output),
        assets=assets,
        limit=args.limit,
        newest_first=not args.file_order,
        state_csv=Path(args.state_file) if args.state_file else None,
        append=args.append,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _load_state(state_csv: Path | None) -> dict:
    state = {"hashes": set(), "embeddings": [], "rows": []}
    if state_csv is None or not state_csv.exists():
        return state

    with state_csv.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            digest = row.get("text_hash", "")
            if digest:
                state["hashes"].add(digest)
            try:
                embedding = json.loads(row.get("embedding_json", "[]"))
            except json.JSONDecodeError:
                embedding = []
            if embedding:
                state["embeddings"].append(embedding)
            state["rows"].append(row)
    return state


def _save_state(state_csv: Path | None, state: dict) -> None:
    if state_csv is None:
        return
    state_csv.parent.mkdir(parents=True, exist_ok=True)
    with state_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=STATE_FIELDNAMES)
        writer.writeheader()
        for row in state["rows"]:
            writer.writerow({field: row.get(field, "") for field in STATE_FIELDNAMES})


def _is_semantic_duplicate(
    embedding: list[float],
    existing_embeddings: list[list[float]],
    threshold: float,
) -> bool:
    return any(cosine_similarity(embedding, existing) >= threshold for existing in existing_embeddings)


def _state_row(event: ProcessedEvent) -> dict[str, str]:
    return {
        "text_hash": event.text_hash,
        "embedding_json": json.dumps(event.embedding),
        "source": event.raw_news.source,
        "title": event.raw_news.title,
        "url": str(event.raw_news.url),
        "published_at": event.raw_news.published_at.isoformat(),
    }


def _state_row_from_news(digest: str, embedding: list[float], news) -> dict[str, str]:
    return {
        "text_hash": digest,
        "embedding_json": json.dumps(embedding),
        "source": news.source,
        "title": clean_text(news.title),
        "url": str(news.url),
        "published_at": news.published_at.isoformat(),
    }


def _load_assets(cli_assets: list[str], assets_file: Path | None) -> list[str]:
    assets = [asset.strip().upper() for asset in cli_assets if asset.strip()]
    if assets_file is not None:
        text = assets_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            clean_line = line.split("#", 1)[0].strip()
            if not clean_line:
                continue
            assets.extend(asset.strip().upper() for asset in clean_line.replace(",", " ").split())
    return list(dict.fromkeys(asset for asset in assets if asset))


def main() -> None:
    parser = argparse.ArgumentParser(description="Process news CSV and export EDMI events to CSV")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--assets-file", help="Path to a file with one or many asset tickers per line")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--file-order", action="store_true")
    parser.add_argument("--state-file", help="Persistent exact and semantic dedup state CSV")
    parser.add_argument("--append", action="store_true", help="Append accepted events to output instead of overwriting it")
    args = parser.parse_args()
    asyncio.run(_run(args))
