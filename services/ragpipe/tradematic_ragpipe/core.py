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
    max_documents: int | None = None,
    max_words: int = 180,
    overlap: int = 40,
    input_csvs: list[Path] | None = None,
    text_inputs: list[Path] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    embeddings = EmbeddingService(settings)
    output_dir.mkdir(parents=True, exist_ok=True)

    documents: list[RagDocument] = []
    source_summaries: list[dict[str, Any]] = []
    csv_inputs = input_csvs or [input_csv]
    for source_index, csv_path in enumerate(csv_inputs, start=1):
        before = len(documents)
        rows_seen = await _append_csv_documents(
            csv_path,
            source_index,
            documents,
            embeddings,
            output_dir,
            limit,
            max_documents,
            max_words,
            overlap,
        )
        source_summaries.append(
            {
                "type": "csv",
                "path": str(csv_path),
                "rows_seen": rows_seen,
                "documents": len(documents) - before,
            }
        )

    for text_index, text_path in enumerate(text_inputs or [], start=1):
        before = len(documents)
        appended = await _append_text_documents(
            text_path,
            text_index,
            documents,
            embeddings,
            output_dir,
            max_documents,
            max_words,
            overlap,
        )
        source_summaries.append(
            {
                "type": "text",
                "path": str(text_path),
                "documents": appended,
            }
        )

    docs_path = output_dir / DOCS_FILE
    save_documents(documents, docs_path)
    save_bm25(documents, output_dir / BM25_FILE)
    faiss_enabled = save_faiss(documents, output_dir / FAISS_FILE)
    save_metadata(documents, output_dir / FAISS_METADATA_FILE)
    chroma_enabled = settings.enable_chroma and upsert_documents(documents, output_dir / "chroma_db")

    return {
        "input_csv": str(input_csv),
        "input_csvs": [str(path) for path in csv_inputs],
        "text_inputs": [str(path) for path in text_inputs or []],
        "output_dir": str(output_dir),
        "docs_jsonl": str(docs_path),
        "bm25": str(output_dir / BM25_FILE),
        "faiss": str(output_dir / FAISS_FILE) if faiss_enabled else "",
        "faiss_metadata": str(output_dir / FAISS_METADATA_FILE),
        "chroma": str(output_dir / "chroma_db") if chroma_enabled else "",
        "memory": str(output_dir / MEMORY_FILE),
        "sources": source_summaries,
        "documents": len(documents),
        "max_documents": max_documents,
        "faiss_enabled": faiss_enabled,
        "chroma_enabled": chroma_enabled,
        "embedding_model": settings.embedding_model,
    }


async def _append_csv_documents(
    input_csv: Path,
    source_index: int,
    documents: list[RagDocument],
    embeddings: EmbeddingService,
    output_dir: Path,
    limit: int | None,
    max_documents: int | None,
    max_words: int,
    overlap: int,
) -> int:
    rows_seen = 0
    source_documents = 0
    for row_number, row in enumerate(iter_csv_rows(input_csv), start=1):
        text = row_text(row)
        if len(text.split()) < 8:
            continue
        title = row.get("title", "").strip() or row.get("asset", "").strip() or input_csv.stem
        source = row.get("source", "").strip() or input_csv.stem
        url = row.get("url", "").strip()
        published_at = row.get("published_at", "").strip()
        loaded_at = row.get("loaded_at", "").strip()
        source_documents += await _append_chunked_document(
            documents,
            embeddings,
            output_dir,
            text=text,
            title=title,
            source=source,
            url=url,
            loaded_at=loaded_at,
            published_at=published_at,
            chunk_prefix=f"csv{source_index}_{row_number}",
            max_documents=max_documents,
            source_documents=source_documents,
            max_words=max_words,
            overlap=overlap,
        )

        rows_seen += 1
        if (limit is not None and rows_seen >= limit) or (
            max_documents is not None and source_documents >= max_documents
        ):
            break
    return rows_seen


async def _append_text_documents(
    input_path: Path,
    source_index: int,
    documents: list[RagDocument],
    embeddings: EmbeddingService,
    output_dir: Path,
    max_documents: int | None,
    max_words: int,
    overlap: int,
) -> int:
    if not input_path.exists():
        return 0
    text = input_path.read_text(encoding="utf-8", errors="ignore")
    if len(text.split()) < 8:
        return 0
    return await _append_chunked_document(
        documents,
        embeddings,
        output_dir,
        text=text,
        title=input_path.stem.replace("_", " ").title(),
        source=input_path.name,
        url=str(input_path),
        loaded_at="",
        published_at="",
        chunk_prefix=f"text{source_index}",
        max_documents=max_documents,
        source_documents=0,
        max_words=max_words,
        overlap=overlap,
    )


async def _append_chunked_document(
    documents: list[RagDocument],
    embeddings: EmbeddingService,
    output_dir: Path,
    *,
    text: str,
    title: str,
    source: str,
    url: str,
    loaded_at: str,
    published_at: str,
    chunk_prefix: str,
    max_documents: int | None,
    source_documents: int,
    max_words: int,
    overlap: int,
) -> int:
    doc_id = document_id(url, title, text)
    appended = 0
    chunks = chunk_text(text, max_words=max_words, overlap=overlap)
    for chunk_number, chunk in enumerate(chunks, start=1):
        if len(chunk.split()) < 8:
            continue
        if max_documents is not None and source_documents + appended >= max_documents:
            break
        embedding = await embeddings.embed(f"{title}\n{chunk}".strip())
        document = RagDocument(
            doc_id=doc_id,
            chunk_id=f"{chunk_prefix}_{chunk_number}",
            text=chunk,
            title=title,
            source=source,
            url=url,
            loaded_at=loaded_at,
            published_at=published_at,
            embedding=embedding,
        )
        documents.append(document)
        appended += 1
        save_event(
            output_dir / MEMORY_FILE,
            chunk,
            {
                "kind": "ragpipe_chunk",
                "source": source,
                "title": title,
                "url": url,
                "loaded_at": document.loaded_at,
                "published_at": document.published_at,
            },
        )
    return appended


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
    input_paths = [Path(path) for path in args.input]
    result = await build_ragpipe_index(
        input_paths[0],
        Path(args.output_dir),
        args.limit,
        args.max_documents,
        args.max_words,
        args.overlap,
        input_paths,
        [Path(path) for path in args.text_input],
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
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--text-input", action="append", default=[])
    parser.add_argument("--output-dir", default=str(default_index_dir()))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-documents", type=int)
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
