from collections import defaultdict
from typing import Protocol
from uuid import UUID

from edmi.domain.models import (
    Entities,
    EventClassification,
    MarketEffect,
    ProcessedEvent,
    RawNews,
    RelevanceClassification,
)
from edmi.services.vector import cosine_similarity


class EventRepository(Protocol):
    async def save_processed_event(self, event: ProcessedEvent) -> None: ...
    async def find_similar_news(self, embedding: list[float], threshold: float) -> UUID | None: ...
    async def find_event_for_embedding(self, embedding: list[float], min_similarity: float) -> UUID | None: ...
    async def list_events_for_asset(self, asset: str) -> list[ProcessedEvent]: ...
    async def list_impacts_for_asset(self, asset: str) -> list[dict]: ...
    async def save_asset_effect(
        self,
        event_id: UUID,
        asset: str,
        relation: RelevanceClassification,
        effect: MarketEffect,
    ) -> None: ...


class InMemoryEventRepository:
    def __init__(self) -> None:
        self.events: dict[UUID, ProcessedEvent] = {}
        self.news_embeddings: dict[UUID, list[float]] = {}
        self.event_embeddings: dict[UUID, list[float]] = {}
        self.asset_index: dict[str, set[UUID]] = defaultdict(set)

    async def save_processed_event(self, event: ProcessedEvent) -> None:
        self.events[event.id] = event
        self.news_embeddings[event.news_id] = event.embedding
        self.event_embeddings[event.id] = event.embedding
        for asset in event.asset_relations:
            self.asset_index[asset.upper()].add(event.id)

    async def find_similar_news(self, embedding: list[float], threshold: float) -> UUID | None:
        for news_id, existing in self.news_embeddings.items():
            if cosine_similarity(embedding, existing) >= threshold:
                return news_id
        return None

    async def find_event_for_embedding(self, embedding: list[float], min_similarity: float) -> UUID | None:
        best_id: UUID | None = None
        best_score = min_similarity
        for event_id, existing in self.event_embeddings.items():
            score = cosine_similarity(embedding, existing)
            if score >= best_score:
                best_id = event_id
                best_score = score
        return best_id

    async def list_events_for_asset(self, asset: str) -> list[ProcessedEvent]:
        ids = self.asset_index.get(asset.upper(), set())
        return [self.events[event_id] for event_id in ids if event_id in self.events]

    async def list_impacts_for_asset(self, asset: str) -> list[dict]:
        result = []
        for event in await self.list_events_for_asset(asset):
            effect = event.market_effects.get(asset.upper())
            relation = event.asset_relations.get(asset.upper())
            if effect and relation:
                result.append(
                    {
                        "event_id": event.id,
                        "asset": asset.upper(),
                        "level": relation.level,
                        "confidence": relation.confidence,
                        "delta_1h": effect.delta_1h,
                        "delta_1d": effect.delta_1d,
                        "impact_1h": effect.impact_1h,
                        "impact_1d": effect.impact_1d,
                        "explanation": effect.explanation,
                    }
                )
        return result

    async def save_asset_effect(
        self,
        event_id: UUID,
        asset: str,
        relation: RelevanceClassification,
        effect: MarketEffect,
    ) -> None:
        event = self.events[event_id]
        normalized = asset.upper()
        event.asset_relations[normalized] = relation
        event.market_effects[normalized] = effect
        self.asset_index[normalized].add(event_id)


class AsyncpgEventRepository:
    def __init__(self, pool) -> None:
        self.pool = pool

    async def save_processed_event(self, event: ProcessedEvent) -> None:
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """
                    INSERT INTO news (
                      id, source, title, text, url, text_hash, embedding, published_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8)
                    ON CONFLICT (text_hash) DO NOTHING
                    """,
                event.news_id,
                event.raw_news.source,
                event.raw_news.title,
                event.raw_news.text,
                str(event.raw_news.url),
                event.text_hash,
                _vector_literal(event.embedding),
                event.raw_news.published_at,
            )
            await connection.execute(
                """
                    INSERT INTO events (
                      id, event_type, confidence, centroid_embedding, entities
                    )
                    VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                      event_type = EXCLUDED.event_type,
                      confidence = EXCLUDED.confidence,
                      centroid_embedding = EXCLUDED.centroid_embedding,
                      entities = EXCLUDED.entities
                    """,
                event.id,
                event.classification.event_type.value,
                event.classification.confidence,
                _vector_literal(event.embedding),
                event.entities.model_dump_json(),
            )
            await connection.execute(
                """
                    INSERT INTO event_news (event_id, news_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                event.id,
                event.news_id,
            )
            for asset, relation in event.asset_relations.items():
                await connection.execute(
                    """
                        INSERT INTO event_asset_relation (
                          event_id, asset, level, confidence, explanation
                        )
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (event_id, asset) DO UPDATE SET
                          level = EXCLUDED.level,
                          confidence = EXCLUDED.confidence,
                          explanation = EXCLUDED.explanation
                        """,
                    event.id,
                    asset,
                    relation.level.value,
                    relation.confidence,
                    relation.explanation,
                )
            for asset, effect in event.market_effects.items():
                await self._save_asset_effect(connection, event.id, asset, effect)

    async def find_similar_news(self, embedding: list[float], threshold: float) -> UUID | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id
                FROM news
                WHERE 1 - (embedding <=> $1::vector) >= $2
                ORDER BY embedding <=> $1::vector
                LIMIT 1
                """,
                _vector_literal(embedding),
                threshold,
            )
        return row["id"] if row else None

    async def find_event_for_embedding(self, embedding: list[float], min_similarity: float) -> UUID | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id
                FROM events
                WHERE 1 - (centroid_embedding <=> $1::vector) >= $2
                ORDER BY centroid_embedding <=> $1::vector
                LIMIT 1
                """,
                _vector_literal(embedding),
                min_similarity,
            )
        return row["id"] if row else None

    async def list_events_for_asset(self, asset: str) -> list[ProcessedEvent]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                  e.id AS event_id,
                  e.event_type,
                  e.confidence AS event_confidence,
                  e.entities,
                  n.id AS news_id,
                  n.source,
                  n.title,
                  n.text,
                  n.url,
                  n.text_hash,
                  n.published_at,
                  r.level,
                  r.confidence AS relation_confidence,
                  r.explanation AS relation_explanation,
                  m.delta_1h,
                  m.delta_1d,
                  m.impact_1h,
                  m.impact_1d,
                  m.explanation AS effect_explanation
                FROM event_asset_relation r
                JOIN events e ON e.id = r.event_id
                JOIN event_news en ON en.event_id = e.id
                JOIN news n ON n.id = en.news_id
                LEFT JOIN event_market_effect m
                  ON m.event_id = e.id AND m.asset = r.asset
                WHERE r.asset = $1
                ORDER BY n.published_at DESC
                """,
                asset.upper(),
            )
        return [_row_to_event(row, asset.upper()) for row in rows]

    async def list_impacts_for_asset(self, asset: str) -> list[dict]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                  r.event_id,
                  r.asset,
                  r.level,
                  r.confidence,
                  m.delta_1h,
                  m.delta_1d,
                  m.impact_1h,
                  m.impact_1d,
                  COALESCE(m.explanation, r.explanation) AS explanation
                FROM event_asset_relation r
                LEFT JOIN event_market_effect m
                  ON m.event_id = r.event_id AND m.asset = r.asset
                WHERE r.asset = $1
                ORDER BY r.event_id DESC
                """,
                asset.upper(),
            )
        return [dict(row) for row in rows]

    async def save_asset_effect(
        self,
        event_id: UUID,
        asset: str,
        relation: RelevanceClassification,
        effect: MarketEffect,
    ) -> None:
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """
                    INSERT INTO event_asset_relation (
                      event_id, asset, level, confidence, explanation
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (event_id, asset) DO UPDATE SET
                      level = EXCLUDED.level,
                      confidence = EXCLUDED.confidence,
                      explanation = EXCLUDED.explanation
                    """,
                event_id,
                asset.upper(),
                relation.level.value,
                relation.confidence,
                relation.explanation,
            )
            await self._save_asset_effect(connection, event_id, asset.upper(), effect)

    @staticmethod
    async def _save_asset_effect(connection, event_id: UUID, asset: str, effect: MarketEffect) -> None:
        await connection.execute(
            """
            INSERT INTO event_market_effect (
              event_id, asset, delta_1h, delta_1d, impact_1h, impact_1d, explanation
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (event_id, asset) DO UPDATE SET
              delta_1h = EXCLUDED.delta_1h,
              delta_1d = EXCLUDED.delta_1d,
              impact_1h = EXCLUDED.impact_1h,
              impact_1d = EXCLUDED.impact_1d,
              explanation = EXCLUDED.explanation
            """,
            event_id,
            asset,
            effect.delta_1h,
            effect.delta_1d,
            effect.impact_1h,
            effect.impact_1d,
            effect.explanation,
        )


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def _row_to_event(row, asset: str) -> ProcessedEvent:
    data = dict(row)
    relation = RelevanceClassification(
        level=data["level"],
        confidence=data["relation_confidence"],
        explanation=data["relation_explanation"],
    )
    effect = MarketEffect(
        delta_1h=data["delta_1h"],
        delta_1d=data["delta_1d"],
        impact_1h=data["impact_1h"],
        impact_1d=data["impact_1d"],
        explanation=data["effect_explanation"] or "",
    )
    return ProcessedEvent(
        id=data["event_id"],
        news_id=data["news_id"],
        raw_news=RawNews(
            source=data["source"],
            title=data["title"],
            text=data["text"],
            url=data["url"],
            published_at=data["published_at"],
        ),
        text_hash=data["text_hash"],
        embedding=[],
        entities=Entities.model_validate_json(data["entities"])
        if isinstance(data["entities"], str)
        else Entities.model_validate(data["entities"]),
        classification=EventClassification(
            event_type=data["event_type"],
            confidence=data["event_confidence"],
        ),
        asset_relations={asset: relation},
        market_effects={asset: effect},
    )
