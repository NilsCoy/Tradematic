from uuid import uuid4

from edmi.config import Settings
from edmi.domain.models import MarketEffect, ProcessedEvent, RawNews, RELEVANCE_WEIGHTS
from edmi.infrastructure.dedup import Deduplicator, text_hash
from edmi.infrastructure.storage import EventRepository
from edmi.ingestion.cleaning import clean_text
from edmi.services.embedding import EmbeddingService
from edmi.services.llm import OllamaLLMService
from edmi.services.market_data import MarketDataService
from edmi.services.ner import NERService


class DuplicateNewsError(Exception):
    """Raised when exact or semantic duplicate news is detected."""


class NewsProcessingPipeline:
    def __init__(
        self,
        settings: Settings,
        repository: EventRepository,
        deduplicator: Deduplicator,
        embedding_service: EmbeddingService,
        ner_service: NERService,
        llm_service: OllamaLLMService,
        market_data_service: MarketDataService,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.deduplicator = deduplicator
        self.embedding_service = embedding_service
        self.ner_service = ner_service
        self.llm_service = llm_service
        self.market_data_service = market_data_service

    async def process(self, news: RawNews, assets: list[str] | None = None) -> ProcessedEvent:
        cleaned = RawNews(
            source=news.source,
            title=clean_text(news.title),
            text=clean_text(news.text),
            url=news.url,
            published_at=news.published_at,
        )
        digest = text_hash(cleaned.text)
        if await self.deduplicator.seen_or_add(digest):
            raise DuplicateNewsError("Exact duplicate news")

        embedding = await self.embedding_service.embed(f"{cleaned.title}\n{cleaned.text}")
        similar_news_id = await self.repository.find_similar_news(embedding, self.settings.semantic_dup_threshold)
        if similar_news_id is not None:
            raise DuplicateNewsError(f"Semantic duplicate news: {similar_news_id}")

        min_cluster_similarity = 1.0 - self.settings.cluster_eps
        event_id = await self.repository.find_event_for_embedding(embedding, min_cluster_similarity)
        entities = await self.ner_service.extract(cleaned.text)
        classification = await self.llm_service.classify_event(cleaned.text, entities)
        processed = ProcessedEvent(
            id=event_id or uuid4(),
            raw_news=cleaned,
            text_hash=digest,
            embedding=embedding,
            entities=entities,
            classification=classification,
        )

        for asset in assets or []:
            normalized = asset.upper()
            relation = await self.llm_service.classify_relevance(cleaned.text, entities, normalized)
            delta_1h = await self.market_data_service.price_delta(normalized, cleaned.published_at, "1h")
            delta_1d = await self.market_data_service.price_delta(normalized, cleaned.published_at, "1d")
            weight = RELEVANCE_WEIGHTS[relation.level.value]
            effect = MarketEffect(
                delta_1h=delta_1h,
                delta_1d=delta_1d,
                impact_1h=delta_1h * weight if delta_1h is not None else None,
                impact_1d=delta_1d * weight if delta_1d is not None else None,
            )
            effect.explanation = await self.llm_service.explain_impact(
                cleaned.text, entities, normalized, relation, delta_1h, delta_1d
            )
            processed.asset_relations[normalized] = relation
            processed.market_effects[normalized] = effect

        await self.repository.save_processed_event(processed)
        return processed
