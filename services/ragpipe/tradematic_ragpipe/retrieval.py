from __future__ import annotations

from pathlib import Path
from typing import Any

from tradematic_ragpipe.bm25_index import BM25_FILE, bm25_scores
from tradematic_ragpipe.chroma_store import query_chroma
from tradematic_ragpipe.documents import RagDocument
from tradematic_ragpipe.faiss_index import FAISS_FILE, faiss_hits
from tradematic_ragpipe.rerank import Reranker
from tradematic_ragpipe.settings import RagpipeSettings
from tradematic_ragpipe.tokenization import tokenize


def keyword_score(query: str, document: str) -> float:
    keywords = tokenize(query)
    if not keywords:
        return 0.0
    document_tokens = set(tokenize(document))
    hits = sum(1 for keyword in keywords if keyword in document_tokens)
    return hits / len(keywords)


def score_boost(document: str) -> float:
    lowered = document.lower()
    score = 0.0
    for marker in ("курс", "ставка", "инфляц", "выручк", "прибыл", "санкц", "нефть", "газ", "цб", "фрс"):
        if marker in lowered:
            score += 0.1
    if len(document) > 500:
        score += 0.1
    return min(score, 1.0)


def hybrid_search(
    index_dir: Path,
    documents: list[RagDocument],
    queries: list[str],
    query_vector: list[float],
    top_k: int,
    settings: RagpipeSettings,
) -> list[tuple[float, RagDocument]]:
    if not documents:
        return []

    scores = {index: 0.0 for index in range(len(documents))}
    for query in queries:
        scores_for_query = bm25_scores(index_dir / BM25_FILE, query)
        max_bm25 = max(scores_for_query) if scores_for_query else 0.0
        for index, score in enumerate(scores_for_query):
            scores[index] += 0.35 * _normalize(score, max_bm25)

        for rank, index in enumerate(faiss_hits(index_dir / FAISS_FILE, query_vector, top_k * 6)):
            if index in scores:
                scores[index] += 0.30 * (1.0 / (rank + 1))

        chroma_hits = query_chroma(index_dir / "chroma_db", query_vector, top_k * 6)
        for hit in chroma_hits:
            chunk_id = str(hit.get("metadata", {}).get("chunk_id", ""))
            for index, document in enumerate(documents):
                if document.chunk_id == chunk_id or document.text == hit.get("text"):
                    scores[index] += 0.20 * float(hit.get("score", 0.0))
                    break

        for index, document in enumerate(documents):
            scores[index] += 0.10 * keyword_score(query, document.text)
            scores[index] += 0.05 * score_boost(document.text)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    candidates = [(score, index, documents[index].text) for index, score in ranked[: max(top_k * 4, top_k)]]
    reranked = Reranker(settings).rerank(queries[0], candidates, top_k)
    return [(score, documents[index]) for score, index, _text in reranked]


def match_payload(score: float, document: RagDocument) -> dict[str, Any]:
    return {
        "score": round(float(score), 6),
        "doc_id": document.doc_id,
        "chunk_id": document.chunk_id,
        "title": document.title,
        "source": document.source,
        "url": document.url,
        "loaded_at": document.loaded_at,
        "published_at": document.published_at,
        "text": document.text,
    }


def _normalize(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return value / max_value
