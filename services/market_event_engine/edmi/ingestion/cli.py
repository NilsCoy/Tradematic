import argparse
import asyncio

from edmi.config import get_settings
from edmi.infrastructure.queue import enqueue_batch
from edmi.ingestion.csv_stream import iter_batches, iter_raw_news


async def ingest(path: str, assets: list[str]) -> None:
    settings = get_settings()
    for batch in iter_batches(iter_raw_news(path), settings.batch_size):
        await enqueue_batch(batch, assets)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--asset", action="append", default=[])
    args = parser.parse_args()
    asyncio.run(ingest(args.path, args.asset))

