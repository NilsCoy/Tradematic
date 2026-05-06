from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.logging import logger, setup_logging
from app.service import NewsAggregationService

setup_logging()

app = FastAPI(title="News Aggregator", version="1.0.0")
service = NewsAggregationService()
app_logger = logger.bind(component="api")


@app.get("/health")
async def health() -> dict[str, str]:
    app_logger.debug("Health check requested")
    return {"status": "ok"}


@app.post("/collect")
async def collect_once() -> dict:
    app_logger.bind(route="/collect").info("Collect once requested")
    return await service.collect_once()


@app.get("/collect/stream")
async def collect_stream() -> StreamingResponse:
    app_logger.bind(route="/collect/stream").info("Streaming collection requested")
    return StreamingResponse(service.stream_collection(), media_type="text/event-stream")


@app.get("/dataset")
async def dataset_preview(limit: int = 20) -> dict:
    app_logger.bind(route="/dataset", limit=limit).debug("Dataset preview requested")
    return {"rows": service.dataset_preview(limit=limit)}
