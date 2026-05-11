from __future__ import annotations

import hashlib
import random

import httpx

from tradematic_ragpipe.settings import RagpipeSettings


class EmbeddingService:
    def __init__(self, settings: RagpipeSettings) -> None:
        self.settings = settings
        self._sentence_model = None

    async def embed(self, text: str) -> list[float]:
        vector = await self._embed_with_ollama(text)
        if vector:
            return vector
        vector = self._embed_with_sentence_transformers(text)
        if vector:
            return vector
        return self._stable_embedding(text)

    async def _embed_with_ollama(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=self.settings.embedding_timeout) as client:
                response = await client.post(
                    f"{self.settings.ollama_url}/api/embeddings",
                    json={"model": self.settings.embedding_model, "prompt": text},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []
        embedding = payload.get("embedding")
        if not isinstance(embedding, list):
            return []
        return [float(value) for value in embedding]

    def _embed_with_sentence_transformers(self, text: str) -> list[float]:
        model = self._load_sentence_model()
        if model is None:
            return []
        vector = model.encode([f"query: {text}"], normalize_embeddings=True)[0]
        return [float(value) for value in vector]

    def _load_sentence_model(self):
        if self._sentence_model is not None:
            return self._sentence_model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return None
        try:
            self._sentence_model = SentenceTransformer(
                "intfloat/multilingual-e5-base",
                local_files_only=self.settings.local_files_only,
            )
        except Exception:
            return None
        return self._sentence_model

    @staticmethod
    def _stable_embedding(text: str, dimensions: int = 768) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
