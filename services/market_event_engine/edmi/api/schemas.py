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


class RagpipeBuildRequest(BaseModel):
    input_path: str | None = None
    input_paths: list[str] = Field(default_factory=list)
    text_inputs: list[str] = Field(default_factory=list)
    index_dir: str | None = None
    limit: int | None = Field(default=None, ge=1)
    max_documents: int | None = Field(default=None, ge=1)
    max_words: int = Field(default=180, ge=20, le=500)
    overlap: int = Field(default=40, ge=0, le=200)


class RagpipeQueryRequest(BaseModel):
    question: str = Field(min_length=1)
    index_dir: str | None = None
    top_k: int = Field(default=6, ge=1, le=20)


class RagpipeChatRequest(RagpipeQueryRequest):
    model: str = "tradematic-analyst"
    ollama_url: str | None = None


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
