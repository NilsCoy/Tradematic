import hashlib
import random

from edmi.config import Settings


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None

    async def embed(self, text: str) -> list[float]:
        model = self._load_model()
        if model is None:
            return self._stable_embedding(text)
        vector = model.encode([f"query: {text}"], normalize_embeddings=True)[0]
        return [float(value) for value in vector]

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return None
        try:
            self._model = SentenceTransformer(
                self.settings.embedding_model,
                local_files_only=self.settings.embedding_local_files_only,
            )
        except (OSError, RuntimeError, ValueError):
            return None
        return self._model

    @staticmethod
    def _stable_embedding(text: str, dimensions: int = 768) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
