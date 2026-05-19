from functools import lru_cache

from redis.asyncio import Redis
from redis.exceptions import RedisError

from edmi.application.pipeline import NewsProcessingPipeline
from edmi.config import get_settings
from edmi.infrastructure.dedup import Deduplicator
from edmi.infrastructure.storage import AsyncpgEventRepository, EventRepository, InMemoryEventRepository
from edmi.services.embedding import EmbeddingService
from edmi.services.llm import OllamaLLMService
from edmi.services.market_data import MarketDataService
from edmi.services.ner import NERService


_postgres_repository: EventRepository | None = None


@lru_cache
def get_memory_repository() -> InMemoryEventRepository:
    return InMemoryEventRepository()


async def get_repository() -> EventRepository:
    global _postgres_repository
    settings = get_settings()
    if not settings.database_url:
        return get_memory_repository()
    if _postgres_repository is not None:
        return _postgres_repository
    try:
        import asyncpg
    except ImportError:
        return get_memory_repository()
    pool = await asyncpg.create_pool(settings.database_url)
    _postgres_repository = AsyncpgEventRepository(pool)
    return _postgres_repository


async def make_redis() -> Redis | None:
    settings = get_settings()
    try:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis.ping()
        return redis
    except (OSError, RedisError):
        return None


async def make_pipeline() -> NewsProcessingPipeline:
    settings = get_settings()
    redis = await make_redis()
    return NewsProcessingPipeline(
        settings=settings,
        repository=await get_repository(),
        deduplicator=Deduplicator(redis),
        embedding_service=EmbeddingService(settings),
        ner_service=NERService(),
        llm_service=OllamaLLMService(settings, redis),
        market_data_service=MarketDataService(settings),
    )
