from __future__ import annotations

import pickle
from pathlib import Path

from tradematic_ragpipe.documents import RagDocument
from tradematic_ragpipe.tokenization import tokenize

BM25_FILE = "ragpipe_bm25.pkl"


def build_bm25(documents: list[RagDocument]):
    from rank_bm25 import BM25Okapi

    tokenized = [tokenize(document.text) for document in documents]
    return BM25Okapi(tokenized), tokenized


def save_bm25(documents: list[RagDocument], path: Path) -> None:
    bm25, tokenized = build_bm25(documents)
    with path.open("wb") as file:
        pickle.dump((bm25, tokenized), file)


def load_bm25(path: Path):
    with path.open("rb") as file:
        return pickle.load(file)


def bm25_scores(path: Path, query: str) -> list[float]:
    if not path.exists():
        return []
    bm25, _tokenized = load_bm25(path)
    return [float(score) for score in bm25.get_scores(tokenize(query))]
