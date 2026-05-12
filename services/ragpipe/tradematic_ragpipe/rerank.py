from __future__ import annotations

from tradematic_ragpipe.settings import RagpipeSettings


class Reranker:
    def __init__(self, settings: RagpipeSettings) -> None:
        self.settings = settings
        self._model = None
        self._load_attempted = False

    def rerank(self, question: str, docs: list[tuple[float, int, str]], top_k: int) -> list[tuple[float, int, str]]:
        if not self.settings.enable_rerank or not docs:
            return docs[:top_k]
        model = self._load_model()
        if model is None:
            return docs[:top_k]
        pairs = [(question, text) for _score, _index, text in docs]
        try:
            scores = model.predict(pairs)
        except Exception:
            return docs[:top_k]
        ranked = [
            (float(scores[position]), docs[position][1], docs[position][2])
            for position in range(len(docs))
        ]
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[:top_k]

    def _load_model(self):
        if self._load_attempted:
            return self._model
        self._load_attempted = True
        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            return None
        try:
            self._model = CrossEncoder(
                self.settings.rerank_model,
                local_files_only=self.settings.local_files_only,
            )
        except Exception:
            self._model = None
        return self._model
