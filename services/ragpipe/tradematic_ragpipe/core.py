from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import pickle
import random
import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


DEFAULT_MODEL = "tradematic-analyst"
DEFAULT_TOP_K = 6
DOCS_FILE = "ragpipe_docs.jsonl"
BM25_FILE = "ragpipe_bm25.pkl"
FAISS_FILE = "ragpipe_faiss.index"
MEMORY_FILE = "ragpipe_memory.jsonl"

STOPWORDS = {
    "а",
    "в",
    "и",
    "или",
    "как",
    "какой",
    "какая",
    "какие",
    "на",
    "не",
    "о",
    "об",
    "по",
    "с",
    "что",
    "это",
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "to",
    "for",
}

SYSTEM_PROMPT = """
Ты финансовый аналитик Tradematic и отвечаешь только на основе RAG-контекста из новостей,
собранных встроенным парсером Tradematic/EDMI.

Правила:
1. Не выдумывай факты вне контекста.
2. Если данных мало, прямо скажи, чего не хватает.
3. Для рыночных вопросов разделяй факт, экономический смысл и возможное влияние.
4. Если в контексте есть числа, даты, источники или URL, используй их аккуратно.
5. Если вопрос не относится к рынкам, экономике, компаниям, активам или новостному фону,
   коротко откажись и объясни, что RAG ограничен финансовым контекстом.

Отвечай на русском языке, кратко и по делу.
""".strip()


@dataclass(frozen=True)
class RagpipeSettings:
    ollama_url: str = "http://localhost:11434"
    tradematic_datasets_dir: Path = Path("main/scripts/datasets")
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_local_files_only: bool = True


class EmbeddingService:
    def __init__(self, settings: RagpipeSettings) -> None:
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
        except Exception:
            return None
        return self._model

    @staticmethod
    def _stable_embedding(text: str, dimensions: int = 768) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]


@dataclass(frozen=True)
class RagDocument:
    doc_id: str
    chunk_id: str
    text: str
    title: str
    source: str
    url: str
    loaded_at: str
    published_at: str
    embedding: list[float]

    def to_json(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "text": self.text,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "loaded_at": self.loaded_at,
            "published_at": self.published_at,
            "embedding": self.embedding,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> RagDocument:
        return cls(
            doc_id=str(payload.get("doc_id", "")),
            chunk_id=str(payload.get("chunk_id", "")),
            text=str(payload.get("text", "")),
            title=str(payload.get("title", "")),
            source=str(payload.get("source", "")),
            url=str(payload.get("url", "")),
            loaded_at=str(payload.get("loaded_at", "")),
            published_at=str(payload.get("published_at", "")),
            embedding=[float(value) for value in payload.get("embedding", [])],
        )


async def build_ragpipe_index(
    input_csv: Path,
    output_dir: Path,
    limit: int | None = None,
    max_words: int = 180,
    overlap: int = 40,
) -> dict[str, Any]:
    settings = get_settings()
    embeddings = EmbeddingService(settings)
    output_dir.mkdir(parents=True, exist_ok=True)

    documents: list[RagDocument] = []
    async for document in _iter_embedded_documents(input_csv, embeddings, limit, max_words, overlap):
        documents.append(document)

    docs_path = output_dir / DOCS_FILE
    with docs_path.open("w", encoding="utf-8") as file:
        for document in documents:
            file.write(json.dumps(document.to_json(), ensure_ascii=False) + "\n")

    bm25_path = output_dir / BM25_FILE
    _save_bm25(documents, bm25_path)

    faiss_path = output_dir / FAISS_FILE
    faiss_enabled = _save_faiss(documents, faiss_path)

    return {
        "input_csv": str(input_csv),
        "output_dir": str(output_dir),
        "docs_jsonl": str(docs_path),
        "bm25": str(bm25_path),
        "faiss": str(faiss_path) if faiss_enabled else "",
        "documents": len(documents),
        "faiss_enabled": faiss_enabled,
    }


async def query_ragpipe(
    index_dir: Path,
    question: str,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    documents = _load_documents(index_dir / DOCS_FILE)
    if not documents:
        return {"question": question, "matches": []}

    settings = get_settings()
    embeddings = EmbeddingService(settings)
    query_vector = await embeddings.embed(question)
    matches = _hybrid_search(index_dir, documents, question, query_vector, top_k)
    return {
        "question": question,
        "matches": [_match_payload(score, document) for score, document in matches],
    }


async def ask_ragpipe(
    index_dir: Path,
    question: str,
    model: str = DEFAULT_MODEL,
    top_k: int = DEFAULT_TOP_K,
    ollama_url: str | None = None,
) -> dict[str, Any]:
    retrieval = await query_ragpipe(index_dir, question, top_k)
    prompt = _chat_prompt(question, retrieval["matches"])
    base_url = (ollama_url or get_settings().ollama_url).rstrip("/")
    answer = await _ollama_generate(base_url, model, prompt)
    _append_memory(index_dir / MEMORY_FILE, question, answer, retrieval["matches"])
    return {"question": question, "answer": answer, "matches": retrieval["matches"], "model": model}


async def stream_ragpipe_answer(
    index_dir: Path,
    question: str,
    model: str = DEFAULT_MODEL,
    top_k: int = DEFAULT_TOP_K,
    ollama_url: str | None = None,
) -> AsyncIterator[str]:
    retrieval = await query_ragpipe(index_dir, question, top_k)
    prompt = _chat_prompt(question, retrieval["matches"])
    base_url = (ollama_url or get_settings().ollama_url).rstrip("/")
    chunks: list[str] = []
    async for chunk in _ollama_generate_stream(base_url, model, prompt):
        chunks.append(chunk)
        yield chunk
    _append_memory(index_dir / MEMORY_FILE, question, "".join(chunks), retrieval["matches"])


async def _iter_embedded_documents(
    input_csv: Path,
    embeddings: EmbeddingService,
    limit: int | None,
    max_words: int,
    overlap: int,
) -> AsyncIterator[RagDocument]:
    count = 0
    for row_number, row in enumerate(_iter_csv_rows(input_csv), start=1):
        text = _row_text(row)
        if len(text.split()) < 8:
            continue
        title = row.get("title", "").strip()
        source = row.get("source", "").strip()
        url = row.get("url", "").strip()
        doc_id = _document_id(url, title, text)

        for chunk_number, chunk in enumerate(chunk_text(text, max_words=max_words, overlap=overlap), start=1):
            if len(chunk.split()) < 8:
                continue
            embedding = await embeddings.embed(f"{title}\n{chunk}".strip())
            yield RagDocument(
                doc_id=doc_id,
                chunk_id=f"{row_number}_{chunk_number}",
                text=chunk,
                title=title,
                source=source,
                url=url,
                loaded_at=row.get("loaded_at", "").strip(),
                published_at=row.get("published_at", "").strip(),
                embedding=embedding,
            )
        count += 1
        if limit is not None and count >= limit:
            break


def chunk_text(text: str, max_words: int = 180, overlap: int = 40) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(max_words - overlap, 1)
    chunks = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + max_words])
        if chunk:
            chunks.append(chunk)
    return chunks


def _iter_csv_rows(input_csv: Path) -> Iterable[dict[str, str]]:
    with input_csv.open("r", encoding="utf-8", newline="") as file:
        yield from csv.DictReader(file)


def _row_text(row: dict[str, str]) -> str:
    text = row.get("text", "").strip()
    if text:
        return _clean_text(text)
    chunks = row.get("chunks", "").strip()
    if not chunks:
        return ""
    try:
        parsed = json.loads(chunks)
        if isinstance(parsed, list):
            return _clean_text("\n".join(str(item) for item in parsed))
    except json.JSONDecodeError:
        pass
    return _clean_text(chunks)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _document_id(url: str, title: str, text: str) -> str:
    digest = hashlib.sha256(f"{url}\n{title}\n{text[:2000]}".encode()).hexdigest()
    return digest[:24]


def _save_bm25(documents: list[RagDocument], path: Path) -> None:
    from rank_bm25 import BM25Okapi

    tokenized = [tokenize(document.text) for document in documents]
    bm25 = BM25Okapi(tokenized)
    with path.open("wb") as file:
        pickle.dump((bm25, tokenized), file)


def _save_faiss(documents: list[RagDocument], path: Path) -> bool:
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


def _load_documents(path: Path) -> list[RagDocument]:
    if not path.exists():
        return []
    documents = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                documents.append(RagDocument.from_json(json.loads(line)))
    return documents


def _hybrid_search(
    index_dir: Path,
    documents: list[RagDocument],
    question: str,
    query_vector: list[float],
    top_k: int,
) -> list[tuple[float, RagDocument]]:
    scores = {index: 0.0 for index in range(len(documents))}
    bm25_path = index_dir / BM25_FILE
    if bm25_path.exists():
        with bm25_path.open("rb") as file:
            bm25, _tokenized = pickle.load(file)
        bm25_scores = bm25.get_scores(tokenize(question))
        max_bm25 = max(float(score) for score in bm25_scores) if len(bm25_scores) else 0.0
        for index, score in enumerate(bm25_scores):
            scores[index] += 0.45 * _normalize(float(score), max_bm25)

    faiss_hits = _faiss_hits(index_dir / FAISS_FILE, query_vector, top_k * 4)
    for rank, index in enumerate(faiss_hits):
        if index in scores:
            scores[index] += 0.35 * (1.0 / (rank + 1))

    for index, document in enumerate(documents):
        if not faiss_hits:
            scores[index] += 0.35 * max(cosine_similarity(query_vector, document.embedding), 0.0)
        scores[index] += 0.15 * keyword_score(question, document.text)
        scores[index] += 0.05 * score_boost(document.text)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [(score, documents[index]) for index, score in ranked[:top_k]]


def _faiss_hits(path: Path, query_vector: list[float], top_k: int) -> list[int]:
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


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[\w.%-]+", text.lower())
        if token not in STOPWORDS and len(token) > 1
    ]


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
    for marker in ("курс", "ставка", "инфляц", "выручк", "прибыл", "санкц", "нефть", "газ"):
        if marker in lowered:
            score += 0.1
    if len(document) > 500:
        score += 0.1
    return min(score, 1.0)


def _normalize(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return value / max_value


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _match_payload(score: float, document: RagDocument) -> dict[str, Any]:
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


def _chat_prompt(question: str, matches: list[dict[str, Any]]) -> str:
    context_blocks = []
    for index, match in enumerate(matches, start=1):
        context_blocks.append(
            "\n".join(
                [
                    f"[{index}] {match.get('title', '')}",
                    f"source={match.get('source', '')}",
                    f"url={match.get('url', '')}",
                    f"published_at={match.get('published_at', '')}",
                    str(match.get("text", ""))[:2200],
                ]
            )
        )
    context = "\n\n---\n\n".join(context_blocks) or "Нет релевантного контекста."
    return f"{SYSTEM_PROMPT}\n\nВопрос:\n{question}\n\nRAG-контекст:\n{context}\n\nОтвет:"


async def _ollama_generate(base_url: str, model: str, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        payload = response.json()
    return str(payload.get("response", "")).strip()


async def _ollama_generate_stream(base_url: str, model: str, prompt: str) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=180.0) as client, client.stream(
        "POST",
        f"{base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": True},
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line:
                continue
            payload = json.loads(line)
            chunk = str(payload.get("response", ""))
            if chunk:
                yield chunk
            if payload.get("done"):
                break


def _append_memory(path: Path, question: str, answer: str, matches: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "question": question,
        "answer": answer,
        "sources": [
            {
                "title": match.get("title", ""),
                "source": match.get("source", ""),
                "url": match.get("url", ""),
            }
            for match in matches
        ],
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def default_index_dir() -> Path:
    settings = get_settings()
    return settings.tradematic_datasets_dir / "ragpipe"


def get_settings() -> RagpipeSettings:
    datasets_dir = os.environ.get("EDMI_TRADEMATIC_DATASETS_DIR", "main/scripts/datasets")
    local_files_only = os.environ.get("EDMI_EMBEDDING_LOCAL_FILES_ONLY", "true").lower()
    return RagpipeSettings(
        ollama_url=os.environ.get("EDMI_OLLAMA_URL", "http://localhost:11434"),
        tradematic_datasets_dir=Path(datasets_dir),
        embedding_model=os.environ.get("EDMI_EMBEDDING_MODEL", "intfloat/multilingual-e5-base"),
        embedding_local_files_only=local_files_only in {"1", "true", "yes", "on"},
    )


async def _build(args: argparse.Namespace) -> None:
    result = await build_ragpipe_index(
        Path(args.input),
        Path(args.output_dir),
        args.limit,
        args.max_words,
        args.overlap,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def _query(args: argparse.Namespace) -> None:
    result = await query_ragpipe(Path(args.index_dir), args.question, args.top_k)
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def _chat(args: argparse.Namespace) -> None:
    if args.stream:
        async for chunk in stream_ragpipe_answer(
            Path(args.index_dir),
            args.question,
            args.model,
            args.top_k,
            args.ollama_url,
        ):
            print(chunk, end="", flush=True)
        print()
        return
    result = await ask_ragpipe(
        Path(args.index_dir),
        args.question,
        args.model,
        args.top_k,
        args.ollama_url,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_main() -> None:
    parser = argparse.ArgumentParser(description="Build Tradematic ragpipe hybrid BM25+FAISS index")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default=str(default_index_dir()))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-words", type=int, default=180)
    parser.add_argument("--overlap", type=int, default=40)
    args = parser.parse_args()
    asyncio.run(_build(args))


def query_main() -> None:
    parser = argparse.ArgumentParser(description="Query Tradematic ragpipe hybrid index")
    parser.add_argument("--index-dir", default=str(default_index_dir()))
    parser.add_argument("--question", required=True)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    args = parser.parse_args()
    asyncio.run(_query(args))


def chat_main() -> None:
    parser = argparse.ArgumentParser(description="Ask Tradematic ragpipe with optional Ollama streaming")
    parser.add_argument("--index-dir", default=str(default_index_dir()))
    parser.add_argument("--question", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--stream", action="store_true")
    args = parser.parse_args()
    asyncio.run(_chat(args))
