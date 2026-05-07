import uvicorn
from fastapi import FastAPI, HTTPException, Query

from edmi.api.schemas import (
    CsvIngestRequest,
    EventResponse,
    NewsAggregatorIngestRequest,
    NewsAggregatorPipelineRequest,
    NewsIngestRequest,
    PortfolioAnalysisResponse,
)
from edmi.application.factory import get_repository, make_pipeline
from edmi.application.pipeline import DuplicateNewsError
from edmi.config import get_settings
from edmi.integration.news_pipeline import IntegratedNewsPipeline, ingest_csv_path
from edmi.services.market_data import MarketDataService


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

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
        assets: list[str] = Query(default_factory=list),
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


def run() -> None:
    uvicorn.run("edmi.api.main:create_app", factory=True, host="0.0.0.0", port=8000)
