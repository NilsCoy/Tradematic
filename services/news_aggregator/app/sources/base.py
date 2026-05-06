from collections.abc import AsyncIterator
from dataclasses import dataclass

from httpx import AsyncClient

from app.models import NewsRecord


@dataclass(slots=True)
class SourceResult:
    source: str
    records: list[NewsRecord]
    errors: list[str]


class SourceCollector:
    source_name: str

    async def collect(self, client: AsyncClient) -> SourceResult:
        raise NotImplementedError

    async def stream_collect(self, client: AsyncClient) -> AsyncIterator[dict]:
        raise NotImplementedError
