import hashlib

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover
    Redis = None  # type: ignore[assignment]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def news_hash(url: str, text: str) -> str:
    normalized_url = " ".join((url or "").strip().split())
    normalized_text = " ".join((text or "").strip().split())
    return text_hash(f"{normalized_url}\n{normalized_text}")


class Deduplicator:
    def __init__(self, redis: "Redis | None" = None, key: str = "edmi:news_hashes") -> None:
        self.redis = redis
        self.key = key
        self._seen: set[str] = set()

    async def seen_or_add(self, digest: str) -> bool:
        if self.redis is None:
            if digest in self._seen:
                return True
            self._seen.add(digest)
            return False
        added = await self.redis.sadd(self.key, digest)
        return added == 0
