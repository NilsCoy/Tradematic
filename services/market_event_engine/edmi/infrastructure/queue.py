from urllib.parse import urlparse

from arq import create_pool
from arq.connections import RedisSettings

from edmi.config import get_settings
from edmi.domain.models import RawNews


def redis_settings_from_url(url: str) -> RedisSettings:
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


async def enqueue_news(news: RawNews, assets: list[str] | None = None) -> None:
    settings = get_settings()
    pool = await create_pool(redis_settings_from_url(settings.redis_url))
    await pool.enqueue_job("process_news", news.model_dump(mode="json"), assets or [])


async def enqueue_batch(batch: list[RawNews], assets: list[str] | None = None) -> None:
    settings = get_settings()
    pool = await create_pool(redis_settings_from_url(settings.redis_url))
    await pool.enqueue_job(
        "process_batch",
        [item.model_dump(mode="json") for item in batch],
        assets or [],
    )
