from edmi.application.factory import make_pipeline
from edmi.application.pipeline import DuplicateNewsError
from edmi.config import get_settings
from edmi.domain.models import RawNews
from edmi.infrastructure.queue import redis_settings_from_url


async def process_news(ctx, payload: dict, assets: list[str] | None = None) -> str:
    pipeline = await make_pipeline()
    try:
        event = await pipeline.process(RawNews.model_validate(payload), assets or [])
    except DuplicateNewsError:
        return "duplicate"
    return str(event.id)


async def process_batch(ctx, payloads: list[dict], assets: list[str] | None = None) -> dict[str, int]:
    accepted = 0
    duplicates = 0
    for payload in payloads:
        result = await process_news(ctx, payload, assets)
        if result == "duplicate":
            duplicates += 1
        else:
            accepted += 1
    return {"accepted": accepted, "duplicates": duplicates}


settings = get_settings()


class WorkerSettings:
    functions = (process_news, process_batch)
    redis_settings = redis_settings_from_url(settings.redis_url)
    max_jobs = settings.queue_max_jobs
    retry_jobs = True
