from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from tradematic_ragpipe.bm25_index import BM25_FILE, save_bm25
from tradematic_ragpipe.chroma_store import upsert_documents
from tradematic_ragpipe.chunking import chunk_text
from tradematic_ragpipe.documents import (
    RagDocument,
    document_id,
    iter_csv_rows,
    load_documents,
    row_text,
    save_documents,
)
from tradematic_ragpipe.embeddings import EmbeddingService
from tradematic_ragpipe.faiss_index import FAISS_FILE, FAISS_METADATA_FILE, save_faiss, save_metadata
from tradematic_ragpipe.memory_store import load_memory, save_answer, save_event
from tradematic_ragpipe.multi_query import generate_queries
from tradematic_ragpipe.retrieval import hybrid_search, match_payload
from tradematic_ragpipe.settings import default_index_dir, get_settings
from tradematic_ragpipe.trend_analysis import detect_trend


DEFAULT_TOP_K = 6
DOCS_FILE = "ragpipe_docs.jsonl"
MEMORY_FILE = "ragpipe_memory.json"

SYSTEM_PROMPT = """
Ты профессиональный финансовый аналитик Tradematic. Отвечай только на основе RAG-контекста,
собранного из новостей, событий EDMI и памяти предыдущих ответов.

Правила:
1. Не выдумывай факты вне контекста.
2. Для рыночных вопросов разделяй факт, экономический смысл и возможное влияние.
3. Если есть точные числа, даты, источники или URL, используй их аккуратно.
4. История и тренд являются вспомогательным контекстом, а не доказательством.
5. Если вопрос не относится к рынкам, экономике, компаниям, активам или новостному фону,
   коротко откажись и объясни ограничение.

Отвечай на русском языке, кратко, но с выводами.
""".strip()


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
    rows_seen = 0
    for row_number, row in enumerate(iter_csv_rows(input_csv), start=1):
        text = row_text(row)
        if len(text.split()) < 8:
            continue
        title = row.get("title", "").strip()
        source = row.get("source", "").strip()
        url = row.get("url", "").strip()
        doc_id = document_id(url, title, text)
        chunks = chunk_text(text, max_words=max_words, overlap=overlap)

        for chunk_number, chunk in enumerate(chunks, start=1):
            if len(chunk.split()) < 8:
                continue
            embedding = await embeddings.embed(f"{title}\n{chunk}".strip())
            document = RagDocument(
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
            documents.append(document)
            save_event(
                output_dir / MEMORY_FILE,
                chunk,
                {
                    "kind": "news_chunk",
                    "source": source,
                    "title": title,
                    "url": url,
                    "loaded_at": document.loaded_at,
                    "published_at": document.published_at,
                },
            )

        rows_seen += 1
        if limit is not None and rows_seen >= limit:
            break

    docs_path = output_dir / DOCS_FILE
    save_documents(documents, docs_path)
    save_bm25(documents, output_dir / BM25_FILE)
    faiss_enabled = save_faiss(documents, output_dir / FAISS_FILE)
    save_metadata(documents, output_dir / FAISS_METADATA_FILE)
    chroma_enabled = settings.enable_chroma and upsert_documents(documents, output_dir / "chroma_db")

    return {
        "input_csv": str(input_csv),
        "output_dir": str(output_dir),
        "docs_jsonl": str(docs_path),
        "bm25": str(output_dir / BM25_FILE),
        "faiss": str(output_dir / FAISS_FILE) if faiss_enabled else "",
        "faiss_metadata": str(output_dir / FAISS_METADATA_FILE),
        "chroma": str(output_dir / "chroma_db") if chroma_enabled else "",
        "memory": str(output_dir / MEMORY_FILE),
        "rows_seen": rows_seen,
        "documents": len(documents),
        "faiss_enabled": faiss_enabled,
        "chroma_enabled": chroma_enabled,
        "embedding_model": settings.embedding_model,
    }


async def query_ragpipe(index_dir: Path, question: str, top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
    documents = load_documents(index_dir / DOCS_FILE)
    if not documents:
        return {"question": question, "queries": [question], "matches": []}

    settings = get_settings()
    embeddings = EmbeddingService(settings)
    queries = await generate_queries(question, settings)
    query_vector = await embeddings.embed(question)
    matches = hybrid_search(index_dir, documents, queries, query_vector, top_k, settings)
    return {
        "question": question,
        "queries": queries,
        "matches": [match_payload(score, document) for score, document in matches],
    }


async def ask_ragpipe(
    index_dir: Path,
    question: str,
    model: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    ollama_url: str | None = None,
) -> dict[str, Any]:
    retrieval = await query_ragpipe(index_dir, question, top_k)
    prompt = _chat_prompt(index_dir, question, retrieval)
    settings = get_settings()
    selected_model = model or settings.chat_model
    answer = await _ollama_generate((ollama_url or settings.ollama_url).rstrip("/"), selected_model, prompt)
    save_answer(index_dir / MEMORY_FILE, question, answer, retrieval["matches"])
    return {
        "question": question,
        "answer": answer,
        "matches": retrieval["matches"],
        "queries": retrieval.get("queries", [question]),
        "model": selected_model,
    }


async def stream_ragpipe_answer(
    index_dir: Path,
    question: str,
    model: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    ollama_url: str | None = None,
) -> AsyncIterator[str]:
    retrieval = await query_ragpipe(index_dir, question, top_k)
    prompt = _chat_prompt(index_dir, question, retrieval)
    settings = get_settings()
    selected_model = model or settings.chat_model
    chunks: list[str] = []
    async for chunk in _ollama_generate_stream((ollama_url or settings.ollama_url).rstrip("/"), selected_model, prompt):
        chunks.append(chunk)
        yield chunk
    save_answer(index_dir / MEMORY_FILE, question, "".join(chunks), retrieval["matches"])


def _chat_prompt(index_dir: Path, question: str, retrieval: dict[str, Any]) -> str:
    matches = retrieval.get("matches", [])
    top_texts = [str(match.get("text", "")) for match in matches]
    trend = "" if "курс" in question.lower() else detect_trend(top_texts)
    memory_items = load_memory(index_dir / MEMORY_FILE)[-5:]

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
    memory_context = "\n".join(str(item.get("text", ""))[:800] for item in memory_items if item.get("text"))
    queries = "\n".join(f"- {query}" for query in retrieval.get("queries", []))
    return f"""
{SYSTEM_PROMPT}

Вопрос:
{question}

Сгенерированные поисковые запросы:
{queries}

АКТУАЛЬНЫЕ ДАННЫЕ:
{context}

ИСТОРИЯ:
{memory_context or "Нет истории."}

ТРЕНД:
{trend or "Не рассчитывался."}

Ответ:
""".strip()


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
    result = await ask_ragpipe(Path(args.index_dir), args.question, args.model, args.top_k, args.ollama_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_main() -> None:
    parser = argparse.ArgumentParser(description="Build Tradematic ragpipe BM25+FAISS+Chroma+Memory index")
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
    parser.add_argument("--model")
    parser.add_argument("--ollama-url")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--stream", action="store_true")
    args = parser.parse_args()
    asyncio.run(_chat(args))
