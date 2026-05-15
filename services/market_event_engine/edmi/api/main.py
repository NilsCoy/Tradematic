import json
import time
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from edmi.api.schemas import (
    CsvIngestRequest,
    EventResponse,
    NewsAggregatorIngestRequest,
    NewsAggregatorPipelineRequest,
    NewsIngestRequest,
    PortfolioAnalysisResponse,
    RagpipeBuildRequest,
    RagpipeChatRequest,
    RagpipeQueryRequest,
)
from edmi.application.factory import get_repository, make_pipeline
from edmi.application.pipeline import DuplicateNewsError
from edmi.config import get_settings
from edmi.integration.news_pipeline import IntegratedNewsPipeline, ingest_csv_path
from edmi.services.market_data import MarketDataService
from tradematic_ragpipe import ask_ragpipe, build_ragpipe_index, default_index_dir, query_ragpipe, stream_ragpipe_answer


RAGPIPE_TOP_K_QUERY = Query(default=6, ge=1, le=20)
PORTFOLIO_ASSETS_QUERY = Query(default_factory=list)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    async def openai_models() -> dict:
        return {
            "object": "list",
            "data": [
                {
                    "id": "tradematic-analyst",
                    "object": "model",
                    "created": 0,
                    "owned_by": "tradematic",
                }
            ],
        }

    @app.post("/v1/chat/completions", response_model=None)
    async def openai_chat_completions(payload: dict):
        question = _last_user_message(payload.get("messages", []))
        if not question:
            raise HTTPException(status_code=400, detail="No user message found")

        model = str(payload.get("model") or "tradematic-analyst")
        top_k = int(payload.get("top_k") or 6)
        index_dir = default_index_dir()
        if payload.get("stream"):
            return StreamingResponse(
                _openai_stream(index_dir, question, model, top_k),
                media_type="text/event-stream",
            )

        result = await ask_ragpipe(index_dir, question, model, top_k)
        return _openai_completion_payload(model, result["answer"])

    @app.post("/ingest/news", response_model=EventResponse)
    async def ingest_news(payload: NewsIngestRequest) -> EventResponse:
        pipeline = await make_pipeline()
        try:
            event = await pipeline.process(payload.news, payload.assets)
        except DuplicateNewsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _to_event_response(event, payload.assets[0] if payload.assets else None)

    @app.post("/ingest/csv")
    async def ingest_csv(payload: CsvIngestRequest) -> dict[str, int]:
        return await ingest_csv_path(
            payload.path,
            payload.assets,
            payload.limit,
            newest_first=False,
            batch_size=settings.batch_size,
        )

    @app.post("/ingest/news-aggregator")
    async def ingest_news_aggregator(payload: NewsAggregatorIngestRequest) -> dict[str, int | str]:
        path = payload.path or str(settings.news_aggregator_csv_path)
        result = await ingest_csv_path(
            path,
            payload.assets,
            payload.limit,
            newest_first=payload.newest_first,
            batch_size=settings.batch_size,
        )
        return {"path": path, **result}

    @app.post("/pipeline/news-aggregator")
    async def run_news_aggregator_pipeline(payload: NewsAggregatorPipelineRequest) -> dict:
        result = await IntegratedNewsPipeline(settings).run(
            assets=payload.assets,
            limit=payload.limit,
            collect=payload.collect,
            newest_first=payload.newest_first,
        )
        return result.model_dump(mode="json")

    @app.post("/ragpipe/build")
    async def build_ragpipe(payload: RagpipeBuildRequest) -> dict:
        input_paths = [Path(path) for path in payload.input_paths]
        if payload.input_path:
            input_paths.insert(0, Path(payload.input_path))
        if not input_paths:
            input_paths = [settings.news_aggregator_csv_path]
        index_dir = Path(payload.index_dir) if payload.index_dir else default_index_dir()
        return await build_ragpipe_index(
            input_csv=input_paths[0],
            output_dir=index_dir,
            limit=payload.limit,
            max_documents=payload.max_documents,
            max_words=payload.max_words,
            overlap=payload.overlap,
            input_csvs=input_paths,
            text_inputs=[Path(path) for path in payload.text_inputs],
        )

    @app.post("/ragpipe/query")
    async def query_ragpipe_api(payload: RagpipeQueryRequest) -> dict:
        index_dir = Path(payload.index_dir) if payload.index_dir else default_index_dir()
        return await query_ragpipe(index_dir, payload.question, payload.top_k)

    @app.post("/ragpipe/chat")
    async def chat_ragpipe(payload: RagpipeChatRequest) -> dict:
        index_dir = Path(payload.index_dir) if payload.index_dir else default_index_dir()
        return await ask_ragpipe(
            index_dir,
            payload.question,
            payload.model,
            payload.top_k,
            payload.ollama_url,
        )

    @app.get("/ragpipe/chat/stream")
    async def stream_ragpipe(
        question: str,
        index_dir: str | None = None,
        model: str = "tradematic-analyst",
        top_k: int = RAGPIPE_TOP_K_QUERY,
        ollama_url: str | None = None,
    ) -> StreamingResponse:
        resolved_index_dir = Path(index_dir) if index_dir else default_index_dir()
        return StreamingResponse(
            stream_ragpipe_answer(resolved_index_dir, question, model, top_k, ollama_url),
            media_type="text/plain; charset=utf-8",
        )

    @app.get("/events/{asset}", response_model=list[EventResponse])
    async def events_for_asset(asset: str) -> list[EventResponse]:
        repository = await get_repository()
        events = await repository.list_events_for_asset(asset)
        return [_to_event_response(event, asset) for event in events]

    @app.get("/impact/{asset}")
    async def impact_for_asset(asset: str) -> list[dict]:
        repository = await get_repository()
        return await repository.list_impacts_for_asset(asset)

    @app.get("/market-data/{asset}/coverage")
    async def market_data_coverage(asset: str) -> dict:
        coverage = await MarketDataService(settings).coverage(asset)
        return {"asset": asset.upper(), "coverage": coverage}

    @app.get("/portfolio/{portfolio_id}/analysis", response_model=PortfolioAnalysisResponse)
    async def portfolio_analysis(
        portfolio_id: str,
        assets: list[str] = PORTFOLIO_ASSETS_QUERY,
    ) -> PortfolioAnalysisResponse:
        repository = await get_repository()
        responses: list[EventResponse] = []
        impacts: list[dict] = []
        for asset in assets:
            events = await repository.list_events_for_asset(asset)
            responses.extend(_to_event_response(event, asset) for event in events)
            impacts.extend(await repository.list_impacts_for_asset(asset))
        return PortfolioAnalysisResponse(
            portfolio_id=portfolio_id,
            assets=[asset.upper() for asset in assets],
            events=responses,
            impacts=impacts,
        )

    return app


def _to_event_response(event, asset: str | None) -> EventResponse:
    normalized = asset.upper() if asset else None
    return EventResponse(
        id=event.id,
        news_id=event.news_id,
        title=event.raw_news.title,
        source=event.raw_news.source,
        url=str(event.raw_news.url),
        published_at=event.raw_news.published_at,
        entities=event.entities,
        classification=event.classification,
        relevance=event.asset_relations.get(normalized) if normalized else None,
        market_effect=event.market_effects.get(normalized) if normalized else None,
    )


def _last_user_message(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                return "\n".join(parts).strip()
    return ""


def _openai_completion_payload(model: str, content: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


async def _openai_stream(index_dir: Path, question: str, model: str, top_k: int):
    completion_id = f"chatcmpl-{uuid4().hex}"
    async for chunk in stream_ragpipe_answer(index_dir, question, model, top_k):
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def run() -> None:
    uvicorn.run("edmi.api.main:create_app", factory=True, host="0.0.0.0", port=8000)
