from __future__ import annotations

from pathlib import Path
from typing import Any

from tradematic_ragpipe.documents import RagDocument


COLLECTION_NAME = "finance"


def upsert_documents(documents: list[RagDocument], chroma_dir: Path) -> bool:
    if not documents:
        return False
    try:
        import chromadb
    except ImportError:
        return False

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    collection.upsert(
        ids=[document.chunk_id for document in documents],
        documents=[document.text for document in documents],
        embeddings=[document.embedding for document in documents],
        metadatas=[
            {
                "doc_id": document.doc_id,
                "chunk_id": document.chunk_id,
                "title": document.title,
                "source": document.source,
                "url": document.url,
                "loaded_at": document.loaded_at,
                "published_at": document.published_at,
            }
            for document in documents
        ],
    )
    return True


def query_chroma(chroma_dir: Path, query_vector: list[float], top_k: int) -> list[dict[str, Any]]:
    if not query_vector:
        return []
    try:
        import chromadb
    except ImportError:
        return []
    try:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(name=COLLECTION_NAME)
        result = collection.query(query_embeddings=[query_vector], n_results=top_k)
    except Exception:
        return []

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    hits = []
    for index, text in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = float(distances[index]) if index < len(distances) else 1.0
        hits.append({"text": text, "metadata": metadata, "score": max(0.0, 1.0 - distance)})
    return hits
