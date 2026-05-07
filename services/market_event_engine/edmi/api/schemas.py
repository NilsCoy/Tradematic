from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from edmi.domain.models import Entities, EventClassification, MarketEffect, RawNews, RelevanceClassification


class NewsIngestRequest(BaseModel):
    news: RawNews
    assets: list[str] = Field(default_factory=list)


class CsvIngestRequest(BaseModel):
    path: str
    assets: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1)


class NewsAggregatorIngestRequest(BaseModel):
    path: str | None = None
    assets: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=5, ge=1)
    newest_first: bool = True


class NewsAggregatorPipelineRequest(BaseModel):
    assets: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=5, ge=1)
    collect: bool = True
    newest_first: bool = True


class EventResponse(BaseModel):
    id: UUID
    news_id: UUID
    title: str
    source: str
    url: str
    published_at: datetime
    entities: Entities
    classification: EventClassification
    relevance: RelevanceClassification | None = None
    market_effect: MarketEffect | None = None


class PortfolioAnalysisResponse(BaseModel):
    portfolio_id: str
    assets: list[str]
    events: list[EventResponse]
    impacts: list[dict]
