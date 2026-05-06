import argparse
import asyncio

from edmi.config import get_settings
from edmi.integration.news_pipeline import IntegratedNewsPipeline


async def run(args) -> None:
    result = await IntegratedNewsPipeline(get_settings()).run(
        assets=args.asset,
        limit=args.limit,
        collect=args.collect,
        newest_first=not args.file_order,
    )
    print(result.model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run parser-to-EDMI integrated pipeline")
    parser.add_argument("--asset", action="append", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--collect", action="store_true", help="Run news_aggregator first")
    parser.add_argument(
        "--file-order",
        action="store_true",
        help="Process CSV in physical file order instead of newest first",
    )
    args = parser.parse_args()
    asyncio.run(run(args))

