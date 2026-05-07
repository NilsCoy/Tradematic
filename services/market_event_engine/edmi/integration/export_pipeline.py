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
from edmi.ingestion.csv_stream import iter_batches, iter_raw_news


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


async def export_processed_events(
    input_csv: Path,
    output_csv: Path,
    assets: list[str],
    limit: int | None,
    newest_first: bool,
) -> dict[str, int | str]:
    settings = get_settings()
    pipeline = await make_pipeline()
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    accepted = 0
    duplicates = 0
    processed = 0
    with output_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for batch in iter_batches(
            iter_raw_news(input_csv, newest_first=newest_first),
            settings.batch_size,
        ):
            for news in batch:
                if limit is not None and processed >= limit:
                    return _summary(input_csv, output_csv, accepted, duplicates, processed)
                try:
                    event = await pipeline.process(news, assets)
                    accepted += 1
                    for row in _event_rows(event, assets):
                        writer.writerow(row)
                except DuplicateNewsError:
                    duplicates += 1
                finally:
                    processed += 1

    return _summary(input_csv, output_csv, accepted, duplicates, processed)


def _event_rows(event: ProcessedEvent, assets: list[str]) -> list[dict]:
    rows = []
    normalized_assets = [asset.upper() for asset in assets] or [""]
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


def _summary(
    input_csv: Path,
    output_csv: Path,
    accepted: int,
    duplicates: int,
    processed: int,
) -> dict[str, int | str]:
    return {
        "input_csv": str(input_csv),
        "output_csv": str(output_csv),
        "accepted": accepted,
        "duplicates": duplicates,
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
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _load_assets(cli_assets: list[str], assets_file: Path | None) -> list[str]:
    assets = [asset.strip().upper() for asset in cli_assets if asset.strip()]
    if assets_file is not None:
        text = assets_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            clean_line = line.split("#", 1)[0].strip()
            if not clean_line:
                continue
            assets.extend(asset.strip().upper() for asset in clean_line.replace(",", " ").split())
    unique_assets = list(dict.fromkeys(asset for asset in assets if asset))
    if not unique_assets:
        raise ValueError("Provide at least one --asset or --assets-file with asset tickers")
    return unique_assets


def main() -> None:
    parser = argparse.ArgumentParser(description="Process news CSV and export EDMI events to CSV")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--assets-file", help="Path to a file with one or many asset tickers per line")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--file-order", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args))
