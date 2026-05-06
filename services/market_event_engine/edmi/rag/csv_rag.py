from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

from edmi.config import get_settings
from edmi.services.embedding import EmbeddingService
from edmi.services.vector import cosine_similarity


INDEX_FIELDS = (
    "doc_id",
    "asset",
    "title",
    "source",
    "url",
    "published_at",
    "event_type",
    "relevance_level",
    "impact_1d",
    "content",
    "embedding_json",
)


async def build_index(input_csv: Path, output_csv: Path, training_jsonl: Path | None = None) -> dict:
    settings = get_settings()
    embeddings = EmbeddingService(settings)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    if training_jsonl is not None:
        training_jsonl.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with input_csv.open("r", encoding="utf-8", newline="") as src:
        reader = csv.DictReader(src)
        with output_csv.open("w", encoding="utf-8", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=INDEX_FIELDS)
            writer.writeheader()
            train_file = (
                training_jsonl.open("w", encoding="utf-8")
                if training_jsonl is not None
                else None
            )
            try:
                for row in reader:
                    content = _content(row)
                    vector = await embeddings.embed(content)
                    doc = {
                        "doc_id": row.get("event_id", "") or row.get("news_id", ""),
                        "asset": row.get("asset", ""),
                        "title": row.get("title", ""),
                        "source": row.get("source", ""),
                        "url": row.get("url", ""),
                        "published_at": row.get("published_at", ""),
                        "event_type": row.get("event_type", ""),
                        "relevance_level": row.get("relevance_level", ""),
                        "impact_1d": row.get("impact_1d", ""),
                        "content": content,
                        "embedding_json": json.dumps(vector),
                    }
                    writer.writerow(doc)
                    if train_file is not None:
                        train_file.write(
                            json.dumps(
                                {
                                    "messages": [
                                        {
                                            "role": "system",
                                            "content": "You are a market event analyst. Use the supplied event facts.",
                                        },
                                        {
                                            "role": "user",
                                            "content": f"Analyze impact for {doc['asset']}: {doc['title']}",
                                        },
                                        {
                                            "role": "assistant",
                                            "content": content,
                                        },
                                    ]
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                    count += 1
            finally:
                if train_file is not None:
                    train_file.close()

    return {
        "input_csv": str(input_csv),
        "output_csv": str(output_csv),
        "training_jsonl": str(training_jsonl) if training_jsonl else "",
        "documents": count,
    }


async def query_index(index_csv: Path, question: str, top_k: int = 5) -> dict:
    settings = get_settings()
    embeddings = EmbeddingService(settings)
    query_vector = await embeddings.embed(question)
    scored = []
    with index_csv.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            vector = json.loads(row["embedding_json"])
            scored.append((cosine_similarity(query_vector, vector), row))
    scored.sort(key=lambda item: item[0], reverse=True)
    matches = [
        {
            "score": score,
            "title": row["title"],
            "source": row["source"],
            "url": row["url"],
            "content": row["content"],
        }
        for score, row in scored[:top_k]
    ]
    return {"question": question, "matches": matches}


def _content(row: dict[str, str]) -> str:
    parts = [
        f"Asset: {row.get('asset', '')}",
        f"Title: {row.get('title', '')}",
        f"Source: {row.get('source', '')}",
        f"Published: {row.get('published_at', '')}",
        f"Event type: {row.get('event_type', '')}",
        f"Relevance: {row.get('relevance_level', '')}",
        f"Impact 1d: {row.get('impact_1d', '')}",
        f"Relevance explanation: {row.get('relevance_explanation', '')}",
        f"Impact explanation: {row.get('impact_explanation', '')}",
        f"Text: {row.get('text', '')[:4000]}",
    ]
    return "\n".join(parts)


async def _build(args: argparse.Namespace) -> None:
    summary = await build_index(
        Path(args.input),
        Path(args.output),
        Path(args.training_jsonl) if args.training_jsonl else None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


async def _query(args: argparse.Namespace) -> None:
    result = await query_index(Path(args.index), args.question, args.top_k)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_main() -> None:
    parser = argparse.ArgumentParser(description="Build CSV-backed RAG index")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--training-jsonl")
    args = parser.parse_args()
    asyncio.run(_build(args))


def query_main() -> None:
    parser = argparse.ArgumentParser(description="Query CSV-backed RAG index")
    parser.add_argument("--index", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(_query(args))

