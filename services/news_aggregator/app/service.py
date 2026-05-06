from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from app.config import CSV_PATH, REQUEST_TIMEOUT, SOURCE_FETCH_CONCURRENCY, USER_AGENT
from app.logging import logger
from app.sources.cbr import CbrCurrencyCollector
from app.sources.news import build_news_collectors
from app.storage import CsvRepository


class NewsAggregationService:
    def __init__(self) -> None:
        self.repository = CsvRepository(CSV_PATH)
        self.news_collectors = build_news_collectors()
        self.currency_collector = CbrCurrencyCollector()
        self.logger = logger.bind(component="service")
        self.logger.debug(
            "News aggregation service initialized",
            news_collectors=len(self.news_collectors),
            currency_source=self.currency_collector.source_name,
        )

    async def stream_collection(self) -> AsyncIterator[str]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "ru,en;q=0.9",
        }
        stream_logger = self.logger.bind(operation="stream_collection")
        stream_logger.info("Starting streaming collection")
        source_summaries: list[dict] = []
        currency_summary: dict[str, int | str] = {}

        async with httpx.AsyncClient(
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            async for event in self._stream_news_collectors(client, stream_logger):
                if event["event"] == "source_summary":
                    source_summaries.append(event["payload"])
                yield self._sse(event["event"], event["payload"])

            currency_records = []
            currency_errors: list[str] = []
            currency_logger = stream_logger.bind(source=self.currency_collector.source_name)
            currency_logger.info("Starting currency collector")

            yield self._sse(
                "status",
                {"source": self.currency_collector.source_name, "message": "Обновляю курсы ЦБ"},
            )

            async for event in self.currency_collector.stream_collect(client):
                if event["event"] == "record":
                    currency_records.append(event["record"])
                    currency_logger.bind(title=event["record"].title).debug(
                        "Currency record collected"
                    )

                    yield self._sse(
                        "record",
                        {
                            "source": self.currency_collector.source_name,
                            "title": event["record"].title,
                            "url": event["record"].url,
                        },
                    )
                else:
                    currency_errors.append(event["message"])
                    currency_logger.bind(event=event["event"]).warning(event["message"])

                    yield self._sse(
                        event["event"],
                        {
                            "source": self.currency_collector.source_name,
                            "message": event["message"],
                        },
                    )

            if currency_records:
                replaced = self.repository.replace_source(
                    self.currency_collector.source_name, currency_records
                )
                currency_logger.bind(records=len(currency_records), replaced=replaced).info(
                    "Currency data replaced in storage"
                )
                saved_message = f"Обновлено валют: {replaced}"
                currency_summary = {
                    "source": self.currency_collector.source_name,
                    "collected": len(currency_records),
                    "saved": replaced,
                    "errors": len(currency_errors),
                    "status": "updated",
                }
            elif currency_errors:
                replaced = 0
                currency_logger.bind(errors=len(currency_errors)).warning(
                    "Currency update skipped, existing rows preserved due to fetch errors"
                )
                saved_message = (
                    "Курсы не обновлены из-за ошибки сети, предыдущие значения сохранены"
                )
                currency_summary = {
                    "source": self.currency_collector.source_name,
                    "collected": len(currency_records),
                    "saved": replaced,
                    "errors": len(currency_errors),
                    "status": "skipped",
                }
            else:
                replaced = 0
                currency_logger.info("Currency source returned no records and no errors")
                saved_message = "Источник валют не вернул новых записей"
                currency_summary = {
                    "source": self.currency_collector.source_name,
                    "collected": 0,
                    "saved": replaced,
                    "errors": 0,
                    "status": "empty",
                }

            yield self._sse(
                "saved",
                {
                    "source": self.currency_collector.source_name,
                    "message": saved_message,
                },
            )
            yield self._sse("currency_summary", currency_summary)

        rows = self.repository.load_all()
        news_saved_total = sum(int(summary["saved"]) for summary in source_summaries)
        news_errors_total = sum(int(summary["errors"]) for summary in source_summaries)
        stream_logger.bind(
            rows_total=len(rows),
            news_sources=len(source_summaries),
            news_saved_total=news_saved_total,
            news_errors_total=news_errors_total,
        ).info("Streaming collection completed")

        yield self._sse(
            "complete",
            {
                "message": "Сбор завершен",
                "rows_total": len(rows),
                "news_sources": len(source_summaries),
                "news_saved_total": news_saved_total,
                "news_errors_total": news_errors_total,
                "currency_status": currency_summary.get("status", "unknown"),
            },
        )

    async def collect_once(self) -> dict:
        collect_logger = self.logger.bind(operation="collect_once")
        collect_logger.info("Single collection requested")

        events = 0
        source_summaries: list[dict] = []
        currency_summary: dict = {}
        completion_summary: dict = {}
        async for event in self.stream_collection():
            parsed = self._parse_sse(event)
            if parsed["event"] == "record":
                events += 1
            elif parsed["event"] == "source_summary":
                source_summaries.append(parsed["data"])
            elif parsed["event"] == "currency_summary":
                currency_summary = parsed["data"]
            elif parsed["event"] == "complete":
                completion_summary = parsed["data"]

        rows = self.repository.load_all()
        collect_logger.bind(
            events=events,
            rows_total=len(rows),
            source_summaries=len(source_summaries),
        ).info("Single collection finished")

        return {
            "status": "ok",
            "rows_total": len(rows),
            "events": events,
            "sources": source_summaries,
            "currency": currency_summary,
            "summary": completion_summary,
        }

    def dataset_preview(self, limit: int = 20) -> list[dict[str, str]]:
        preview = self.repository.load_all()[:limit]
        self.logger.bind(operation="dataset_preview", limit=limit, rows=len(preview)).debug(
            "Dataset preview prepared"
        )

        return preview

    def _sse(self, event: str, payload: dict) -> str:
        self.logger.bind(operation="sse", event=event).debug("Encoding SSE event")

        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def _stream_news_collectors(
        self,
        client: httpx.AsyncClient,
        stream_logger,
    ) -> AsyncIterator[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        semaphore = asyncio.Semaphore(SOURCE_FETCH_CONCURRENCY)
        tasks = [
            asyncio.create_task(self._run_news_collector(collector, client, queue, semaphore))
            for collector in self.news_collectors
        ]
        completed = 0

        while completed < len(tasks):
            item = await queue.get()
            if item["kind"] == "event":
                yield item["payload"]
                continue

            if item["kind"] == "result":
                completed += 1
                result = item["payload"]
                collector_logger = stream_logger.bind(source=result["source"])
                inserted = self.repository.append_news(result["records"])
                collector_logger.bind(
                    collected=len(result["records"]),
                    inserted=inserted,
                    errors=len(result["errors"]),
                ).info("Collector data saved")
                yield {
                    "event": "saved",
                    "payload": {
                        "source": result["source"],
                        "message": f"Сохранено новых статей: {inserted}",
                    },
                }
                yield {
                    "event": "source_summary",
                    "payload": {
                        "source": result["source"],
                        "collected": len(result["records"]),
                        "saved": inserted,
                        "errors": len(result["errors"]),
                    },
                }

        await asyncio.gather(*tasks)

    async def _run_news_collector(
        self,
        collector,
        client: httpx.AsyncClient,
        queue: asyncio.Queue,
        semaphore: asyncio.Semaphore,
    ) -> None:
        records = []
        errors: list[str] = []
        collector_logger = self.logger.bind(operation="source_runner", source=collector.source_name)

        async with semaphore:
            collector_logger.info("Starting collector")
            await queue.put(
                {
                    "kind": "event",
                    "payload": {
                        "event": "status",
                        "payload": {"source": collector.source_name, "message": "Начинаю сбор"},
                    },
                }
            )

            async for event in collector.stream_collect(client):
                if event["event"] == "record":
                    records.append(event["record"])
                    collector_logger.bind(url=event["record"].url).debug("Record collected")
                    await queue.put(
                        {
                            "kind": "event",
                            "payload": {
                                "event": "record",
                                "payload": {
                                    "source": collector.source_name,
                                    "title": event["record"].title,
                                    "url": event["record"].url,
                                },
                            },
                        }
                    )
                else:
                    errors.append(event["message"])
                    collector_logger.bind(event=event["event"]).warning(event["message"])
                    await queue.put(
                        {
                            "kind": "event",
                            "payload": {
                                "event": event["event"],
                                "payload": {
                                    "source": collector.source_name,
                                    "message": event["message"],
                                },
                            },
                        }
                    )

        await queue.put(
            {
                "kind": "result",
                "payload": {
                    "source": collector.source_name,
                    "records": records,
                    "errors": errors,
                },
            }
        )

    def _parse_sse(self, raw_event: str) -> dict:
        event_name = ""
        data: dict = {}
        for line in raw_event.strip().splitlines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ").strip()
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: ").strip())
        return {"event": event_name, "data": data}
