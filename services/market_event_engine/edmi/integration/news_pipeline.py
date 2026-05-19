from __future__ import annotations

import ast
import asyncio
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from edmi.application.factory import make_pipeline
from edmi.application.pipeline import DuplicateNewsError
from edmi.config import Settings
from edmi.ingestion.csv_stream import iter_batches, iter_raw_news
from edmi.services.market_data import MarketDataService


class ParserRunResult(BaseModel):
    ran: bool
    return_code: int | None = None
    summary: dict[str, Any] | None = None
    log_path: str | None = None
    log_tail: list[str] = Field(default_factory=list)


class IntegratedPipelineResult(BaseModel):
    parser: ParserRunResult
    csv_path: str
    assets: list[str]
    accepted: int
    duplicates: int
    processed: int
    newest_first: bool
    market_data_coverage: dict[str, list[dict]] = Field(default_factory=dict)


class NewsAggregatorRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def collect_once(self) -> ParserRunResult:
        project_dir = _resolve_path(self.settings.news_aggregator_dir)
        with tempfile.NamedTemporaryFile(
            mode="w+",
            encoding="utf-8",
            prefix="edmi-news-aggregator-",
            suffix=".log",
            delete=False,
        ) as log_file:
            log_path = Path(log_file.name)
            code = (
                "import asyncio; "
                "from app.service import NewsAggregationService; "
                "print(asyncio.run(NewsAggregationService().collect_once()))"
            )
            process = await asyncio.create_subprocess_exec(
                "uv",
                "run",
                "python",
                "-c",
                code,
                cwd=str(project_dir),
                stdout=log_file,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                return_code = await asyncio.wait_for(
                    process.wait(),
                    timeout=self.settings.news_aggregator_collect_timeout_seconds,
                )
            except TimeoutError:
                process.kill()
                return_code = await process.wait()

        tail = _tail_lines(log_path)
        return ParserRunResult(
            ran=True,
            return_code=return_code,
            summary=_parse_summary(tail),
            log_path=str(log_path),
            log_tail=tail,
        )


class IntegratedNewsPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.parser_runner = NewsAggregatorRunner(settings)

    async def run(
        self,
        assets: list[str],
        limit: int | None,
        collect: bool,
        newest_first: bool = True,
    ) -> IntegratedPipelineResult:
        parser_result = (
            await self.parser_runner.collect_once()
            if collect
            else ParserRunResult(ran=False)
        )
        csv_path = _resolve_path(self.settings.news_aggregator_csv_path)
        ingestion = await ingest_csv_path(
            path=csv_path,
            assets=assets,
            limit=limit,
            newest_first=newest_first,
            batch_size=self.settings.batch_size,
        )
        return IntegratedPipelineResult(
            parser=parser_result,
            csv_path=str(csv_path),
            assets=[asset.upper() for asset in assets],
            newest_first=newest_first,
            market_data_coverage=await self._market_data_coverage(assets),
            **ingestion,
        )

    async def _market_data_coverage(self, assets: list[str]) -> dict[str, list[dict]]:
        market_data = MarketDataService(self.settings)
        return {
            asset.upper(): await market_data.coverage(asset)
            for asset in assets
        }


async def ingest_csv_path(
    path: str | Path,
    assets: list[str],
    limit: int | None,
    newest_first: bool,
    batch_size: int,
) -> dict[str, int]:
    pipeline = await make_pipeline()
    accepted = 0
    duplicates = 0
    processed = 0
    for batch in iter_batches(
        iter_raw_news(path, newest_first=newest_first),
        batch_size,
    ):
        for news in batch:
            if limit is not None and processed >= limit:
                return {
                    "accepted": accepted,
                    "duplicates": duplicates,
                    "processed": processed,
                }
            try:
                await pipeline.process(news, assets)
                accepted += 1
            except DuplicateNewsError:
                duplicates += 1
            finally:
                processed += 1
    return {"accepted": accepted, "duplicates": duplicates, "processed": processed}


def _resolve_path(path: str | Path) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = (Path.cwd() / resolved).resolve()
    return resolved


def _tail_lines(path: Path, limit: int = 40) -> list[str]:
    lines: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return list(lines)


def _parse_summary(lines: list[str]) -> dict[str, Any] | None:
    for line in reversed(lines):
        if not line.startswith("{"):
            continue
        try:
            value = ast.literal_eval(line)
        except (SyntaxError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return None
