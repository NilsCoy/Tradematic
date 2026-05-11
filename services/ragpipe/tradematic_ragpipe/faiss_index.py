from __future__ import annotations

import pickle
from pathlib import Path

from tradematic_ragpipe.documents import RagDocument

FAISS_FILE = "ragpipe_faiss.index"
FAISS_METADATA_FILE = "ragpipe_faiss_docs.pkl"


def save_metadata(documents: list[RagDocument], path: Path) -> None:
    with path.open("wb") as file:
        pickle.dump([document.to_json() for document in documents], file)


def load_metadata(path: Path) -> list[dict]:
    with path.open("rb") as file:
        return pickle.load(file)


def save_faiss(documents: list[RagDocument], path: Path) -> bool:
    if not documents:
        return False
    try:
        import faiss
        import numpy as np
    except ImportError:
        return False
    vectors = [document.embedding for document in documents if document.embedding]
    if not vectors:
        return False
    index = faiss.IndexFlatIP(len(vectors[0]))
    index.add(np.array(vectors, dtype="float32"))
    faiss.write_index(index, str(path))
    return True


def faiss_hits(path: Path, query_vector: list[float], top_k: int) -> list[int]:
    if not path.exists() or not query_vector:
        return []
    try:
        import faiss
        import numpy as np
    except ImportError:
        return []
    index = faiss.read_index(str(path))
    _distances, indices = index.search(np.array([query_vector], dtype="float32"), top_k)
    return [int(index_value) for index_value in indices[0] if int(index_value) >= 0]
