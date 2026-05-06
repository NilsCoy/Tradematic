from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


class EventType(StrEnum):
    earnings = "earnings"
    product_launch = "product_launch"
    regulation = "regulation"
    macro = "macro"
    geopolitics = "geopolitics"
    supply_chain = "supply_chain"


class RelevanceLevel(StrEnum):
    direct = "direct"
    industry = "industry"
    supply_chain = "supply_chain"
    macro = "macro"
    global_ = "global"
    noise = "noise"


RELEVANCE_WEIGHTS: dict[str, float] = {
    "direct": 1.0,
    "industry": 0.7,
    "supply_chain": 0.5,
    "macro": 0.3,
    "global": 0.2,
    "noise": 0.0,
}


class RawNews(BaseModel):
    source: str
    title: str
    text: str
    url: str | HttpUrl
    published_at: datetime

    @field_validator("source", "title", "text", mode="before")
    @classmethod
    def strip_text_fields(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("published_at")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Entities(BaseModel):
    companies: list[str] = Field(default_factory=list)
    commodities: list[str] = Field(default_factory=list)
    macro: list[str] = Field(default_factory=list)


class EventClassification(BaseModel):
    event_type: EventType
    confidence: float = Field(ge=0.0, le=1.0)


class RelevanceClassification(BaseModel):
    level: RelevanceLevel
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = ""


class MarketEffect(BaseModel):
    delta_1h: float | None = None
    delta_1d: float | None = None
    impact_1h: float | None = None
    impact_1d: float | None = None
    explanation: str = ""


class ProcessedEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    news_id: UUID = Field(default_factory=uuid4)
    raw_news: RawNews
    text_hash: str
    embedding: list[float]
    entities: Entities
    classification: EventClassification
    asset_relations: dict[str, RelevanceClassification] = Field(default_factory=dict)
    market_effects: dict[str, MarketEffect] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Portfolio(BaseModel):
    id: str
    assets: list[str]

