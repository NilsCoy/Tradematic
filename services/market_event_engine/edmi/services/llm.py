import hashlib
import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from edmi.config import Settings
from edmi.domain.models import (
    Entities,
    EventClassification,
    EventType,
    RelevanceClassification,
    RelevanceLevel,
)

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover
    Redis = None  # type: ignore[assignment]


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class OllamaLLMService:
    def __init__(self, settings: Settings, redis: "Redis | None" = None) -> None:
        self.settings = settings
        self.redis = redis

    async def classify_event(self, text: str, entities: Entities) -> EventClassification:
        prompt = (
            "Classify the market news event as JSON with event_type and confidence. "
            f"Allowed event_type values: {[item.value for item in EventType]}. "
            f"Entities: {entities.model_dump_json()}\nText: {text[:4000]}"
        )
        fallback = self._heuristic_event(text)
        return await self._json_call(prompt, EventClassification, fallback)

    async def classify_relevance(
        self, text: str, entities: Entities, asset: str
    ) -> RelevanceClassification:
        prompt = (
            "Classify relevance of this event to the asset as JSON with level, confidence, "
            "and explanation. "
            f"Allowed level values: {[item.value for item in RelevanceLevel]}. "
            f"Asset: {asset}. Entities: {entities.model_dump_json()}\nText: {text[:4000]}"
        )
        fallback = self._heuristic_relevance(text, entities, asset)
        return await self._json_call(prompt, RelevanceClassification, fallback)

    async def explain_impact(
        self,
        text: str,
        entities: Entities,
        asset: str,
        relevance: RelevanceClassification,
        delta_1h: float | None,
        delta_1d: float | None,
    ) -> str:
        prompt = (
            "Explain the market impact in one concise paragraph. "
            f"Asset={asset}, relevance={relevance.model_dump()}, "
            f"delta_1h={delta_1h}, delta_1d={delta_1d}, "
            f"entities={entities.model_dump_json()}, text={text[:2500]}"
        )
        cache_key = self._cache_key("explain", prompt)
        cached = await self._cache_get(cache_key)
        if cached:
            return cached
        try:
            payload = await self._ollama_generate(prompt)
            explanation = str(payload.get("response", "")).strip()
        except (httpx.HTTPError, ValueError):
            explanation = relevance.explanation or "Market effect is estimated from observed price deltas and event relevance."
        await self._cache_set(cache_key, explanation)
        return explanation

    async def _json_call(self, prompt: str, schema: type[SchemaT], fallback: SchemaT) -> SchemaT:
        cache_key = self._cache_key(schema.__name__, prompt)
        cached = await self._cache_get(cache_key)
        if cached:
            try:
                return schema.model_validate_json(cached)
            except ValidationError:
                pass
        try:
            payload = await self._ollama_generate(prompt + "\nReturn JSON only.")
            data = self._extract_json(str(payload.get("response", "")))
            parsed = schema.model_validate(data)
        except (httpx.HTTPError, ValueError, ValidationError, json.JSONDecodeError):
            parsed = fallback
        await self._cache_set(cache_key, parsed.model_dump_json())
        return parsed

    async def _ollama_generate(self, prompt: str) -> dict:
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
            for _ in range(3):
                try:
                    response = await client.post(
                        f"{self.settings.ollama_url.rstrip('/')}/api/generate",
                        json={
                            "model": self.settings.ollama_model,
                            "prompt": prompt,
                            "stream": False,
                            "format": "json" if "Return JSON only" in prompt else None,
                        },
                    )
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPError as exc:
                    last_error = exc
        raise last_error or ValueError("Ollama request failed")

    @staticmethod
    def _extract_json(value: str) -> dict:
        start = value.find("{")
        end = value.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("LLM response does not contain JSON")
        return json.loads(value[start : end + 1])

    async def _cache_get(self, key: str) -> str | None:
        if self.redis is None:
            return None
        value = await self.redis.get(key)
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    async def _cache_set(self, key: str, value: str) -> None:
        if self.redis is not None:
            await self.redis.set(key, value, ex=60 * 60 * 24)

    @staticmethod
    def _cache_key(prefix: str, prompt: str) -> str:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return f"edmi:llm:{prefix}:{digest}"

    @staticmethod
    def _heuristic_event(text: str) -> EventClassification:
        lower = text.lower()
        if any(word in lower for word in ("earnings", "revenue", "profit", "отчет", "прибыль")):
            event_type = EventType.earnings
        elif any(word in lower for word in ("launch", "release", "запуск", "продукт")):
            event_type = EventType.product_launch
        elif any(word in lower for word in ("regulation", "sanction", "law", "регуля", "закон")):
            event_type = EventType.regulation
        elif any(word in lower for word in ("inflation", "rate", "gdp", "инфляц", "ставк")):
            event_type = EventType.macro
        elif any(word in lower for word in ("war", "conflict", "geopolit", "войн", "конфликт")):
            event_type = EventType.geopolitics
        else:
            event_type = EventType.supply_chain
        return EventClassification(event_type=event_type, confidence=0.55)

    @staticmethod
    def _heuristic_relevance(text: str, entities: Entities, asset: str) -> RelevanceClassification:
        lower = text.lower()
        asset_lower = asset.lower()
        company_hit = any(asset_lower in company.lower() for company in entities.companies)
        if asset_lower in lower or company_hit:
            level = RelevanceLevel.direct
            explanation = "The asset is explicitly mentioned in the event."
        elif entities.macro:
            level = RelevanceLevel.macro
            explanation = "The event contains macroeconomic drivers that can affect the asset."
        elif entities.commodities:
            level = RelevanceLevel.industry
            explanation = "The event mentions commodities or industry factors related to the asset."
        else:
            level = RelevanceLevel.noise
            explanation = "No clear asset-specific link was found."
        return RelevanceClassification(level=level, confidence=0.5, explanation=explanation)

