from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path

import httpx

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

DEFAULT_ANALYST_MODEL = "tradematic-analyst"
MARKET_ASSET = "MARKET"
BRIEF_CATEGORIES = (
    {
        "key": "executive",
        "title": "Executive overview",
        "event_types": (),
        "focus": "общая картина дня, главные драйверы, баланс позитивных и негативных сигналов",
    },
    {
        "key": "macro_economy",
        "title": "Macro and economy",
        "event_types": ("macro", "regulation"),
        "focus": "макроэкономика, ставки, инфляция, регуляторы, бюджетные и валютные риски",
    },
    {
        "key": "geopolitics",
        "title": "Geopolitics",
        "event_types": ("geopolitics",),
        "focus": "геополитика, санкции, международная напряженность и страновые риски",
    },
    {
        "key": "corporate",
        "title": "Corporate and earnings",
        "event_types": ("earnings", "product_launch"),
        "focus": "корпоративные новости, отчетность, продукты, сделки и управленческие решения",
    },
    {
        "key": "commodities_supply_chain",
        "title": "Commodities and supply chain",
        "event_types": ("supply_chain",),
        "focus": "сырье, логистика, производство, поставки, энергия и себестоимость",
    },
    {
        "key": "risk_watch",
        "title": "Risk watch",
        "event_types": (),
        "focus": "ключевые риски, слабые сигналы, противоречия в данных и что аналитику проверить вручную",
    },
)
SOURCE_LIKE_ASSETS = {
    "AP",
    "AP PHOTO",
    "APPSTORE",
    "BBC",
    "BLOOMBERG",
    "CNBC",
    "DW",
    "EURONEWS",
    "FORBES",
    "GUARDIAN",
    "LENTA.RU",
    "REUTERS",
    "RIA",
    "RIA.RU",
    "RT",
    "SPUTNIK",
    "ТАСС",
}
DEFAULT_SYSTEM_PROMPT = """
Ты аналитик Tradematic. Отвечай только на основе переданного RAG-контекста из новостей,
обработанных EDMI. Для каждого актива дай краткий вывод: ключевые события, направление
влияния, уровень уверенности, риски и что стоит проверить дальше. Если данных мало, прямо
скажи об этом и не выдумывай факты.
""".strip()


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


async def analyze_assets(
    index_csv: Path,
    assets: list[str],
    output_json: Path,
    output_md: Path,
    model: str = DEFAULT_ANALYST_MODEL,
    ollama_url: str | None = None,
    top_k: int = 8,
) -> dict:
    rows = _read_index(index_csv)
    available_assets = _available_assets(rows)
    target_assets = assets or available_assets
    if not target_assets:
        target_assets = [MARKET_ASSET]

    settings = get_settings()
    base_url = (ollama_url or settings.ollama_url).rstrip("/")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    analyses = []
    for asset in target_assets:
        matches = _top_asset_rows(rows, asset, top_k)
        prompt = _analysis_prompt(asset, matches)
        answer = await _ollama_generate(base_url, model, prompt)
        analyses.append(
            {
                "asset": asset,
                "model": model,
                "documents": len(matches),
                "analysis": answer,
                "sources": [
                    {
                        "title": row.get("title", ""),
                        "source": row.get("source", ""),
                        "url": row.get("url", ""),
                        "published_at": row.get("published_at", ""),
                        "event_type": row.get("event_type", ""),
                        "impact_1d": row.get("impact_1d", ""),
                    }
                    for row in matches
                ],
            }
        )

    payload = {
        "index_csv": str(index_csv),
        "model": model,
        "assets": target_assets,
        "analyses": analyses,
    }
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(_analysis_markdown(analyses), encoding="utf-8")
    return {
        "index_csv": str(index_csv),
        "output_json": str(output_json),
        "output_md": str(output_md),
        "model": model,
        "assets": target_assets,
        "analyses": len(analyses),
    }


async def brief_market(
    index_csv: Path,
    output_json: Path,
    output_md: Path,
    model: str = DEFAULT_ANALYST_MODEL,
    ollama_url: str | None = None,
    top_k: int = 10,
) -> dict:
    rows = _latest_rows(_read_index(index_csv))
    settings = get_settings()
    base_url = (ollama_url or settings.ollama_url).rstrip("/")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    async def run_category(category: dict) -> dict:
        selected = _category_rows(rows, category["event_types"], top_k)
        prompt = _brief_prompt(category["title"], category["focus"], selected)
        answer = await _ollama_generate(base_url, model, prompt)
        return {
            "key": category["key"],
            "title": category["title"],
            "focus": category["focus"],
            "model": model,
            "documents": len(selected),
            "summary": answer,
            "sources": _sources(selected),
        }

    categories = await asyncio.gather(*(run_category(category) for category in BRIEF_CATEGORIES))
    payload = {
        "index_csv": str(index_csv),
        "model": model,
        "categories": categories,
    }
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(_brief_markdown(categories), encoding="utf-8")
    return {
        "index_csv": str(index_csv),
        "output_json": str(output_json),
        "output_md": str(output_md),
        "model": model,
        "categories": len(categories),
    }


def load_assets(cli_assets: list[str], assets_file: Path | None = None) -> list[str]:
    assets = [asset.strip().upper() for asset in cli_assets if asset.strip()]
    if assets_file is not None:
        text = assets_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            clean_line = line.split("#", 1)[0].strip()
            if not clean_line:
                continue
            assets.extend(asset.strip().upper() for asset in clean_line.replace(",", " ").split())
    return list(dict.fromkeys(asset for asset in assets if asset))


def write_modelfile(output: Path, base_model: str = "llama3.1") -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    content = f'FROM {base_model}\n\nSYSTEM """{DEFAULT_SYSTEM_PROMPT}"""\n'
    output.write_text(content, encoding="utf-8")
    return {
        "output": str(output),
        "base_model": base_model,
        "model_role": "Tradematic RAG analyst",
    }


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


def _read_index(index_csv: Path) -> list[dict[str, str]]:
    with index_csv.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _latest_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: row.get("published_at", ""), reverse=True)


def _category_rows(rows: list[dict[str, str]], event_types: tuple[str, ...], top_k: int) -> list[dict[str, str]]:
    if event_types:
        selected = [row for row in rows if row.get("event_type", "") in event_types]
        if selected:
            return selected[:top_k]
    return rows[:top_k]


def _available_assets(rows: list[dict[str, str]]) -> list[str]:
    assets = []
    for row in rows:
        asset = row.get("asset", "").strip().upper()
        if asset and not _is_noise_asset(asset):
            assets.append(asset)
    return sorted(dict.fromkeys(assets))


def _is_noise_asset(asset: str) -> bool:
    if asset == MARKET_ASSET:
        return False
    if asset in SOURCE_LIKE_ASSETS:
        return True
    if "." in asset:
        return True
    if len(asset.split()) > 2:
        return True
    return False


def _top_asset_rows(rows: list[dict[str, str]], asset: str, top_k: int) -> list[dict[str, str]]:
    exact = [row for row in rows if row.get("asset", "").upper() == asset.upper()]
    selected = exact or rows
    return selected[:top_k]


def _analysis_prompt(asset: str, rows: list[dict[str, str]]) -> str:
    context_blocks = []
    for index, row in enumerate(rows, start=1):
        context_blocks.append(
            "\n".join(
                [
                    f"[{index}] {row.get('title', '')}",
                    f"source={row.get('source', '')}",
                    f"url={row.get('url', '')}",
                    f"published_at={row.get('published_at', '')}",
                    f"event_type={row.get('event_type', '')}",
                    f"impact_1d={row.get('impact_1d', '')}",
                    row.get("content", "")[:2500],
                ]
            )
        )
    context = "\n\n---\n\n".join(context_blocks) or "Нет найденных документов."
    return f"""
Актив: {asset}

RAG-контекст:
{context}

Сделай анализ на русском языке: оцени влияние всего новостного фона из RAG-контекста на указанный актив.
1. Ключевые новости и события.
2. Вероятное влияние на цену.
3. Уверенность и ограничения данных.
4. Практический вывод для мониторинга.
""".strip()


def _brief_prompt(title: str, focus: str, rows: list[dict[str, str]]) -> str:
    context_blocks = []
    for index, row in enumerate(rows, start=1):
        context_blocks.append(
            "\n".join(
                [
                    f"[{index}] {row.get('title', '')}",
                    f"source={row.get('source', '')}",
                    f"url={row.get('url', '')}",
                    f"published_at={row.get('published_at', '')}",
                    f"event_type={row.get('event_type', '')}",
                    row.get("content", "")[:2200],
                ]
            )
        )
    context = "\n\n---\n\n".join(context_blocks) or "Нет найденных документов."
    return f"""
Ты старший экономический аналитик Tradematic. Отвечай только на основе RAG-контекста.

Категория: {title}
Фокус анализа: {focus}

RAG-контекст:
{context}

Сформируй сводку на русском языке для человека-аналитика:
1. Ключевые события и сигналы.
2. Экономический смысл и возможные рыночные последствия.
3. Риски, неопределенность и противоречия.
4. Что нужно проверить вручную.

Не выдумывай факты вне контекста. Если данных мало, прямо скажи об этом.
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


def _analysis_markdown(analyses: list[dict]) -> str:
    lines = ["# Tradematic Asset Analysis", ""]
    for item in analyses:
        lines.extend(
            [
                f"## {item['asset']}",
                "",
                item["analysis"].strip(),
                "",
                "Sources:",
            ]
        )
        for source in item["sources"]:
            title = source.get("title") or "Untitled"
            url = source.get("url") or ""
            lines.append(f"- {title} ({source.get('source', '')}) {url}".rstrip())
        lines.append("")
    return "\n".join(lines)


def _sources(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "title": row.get("title", ""),
            "source": row.get("source", ""),
            "url": row.get("url", ""),
            "published_at": row.get("published_at", ""),
            "event_type": row.get("event_type", ""),
        }
        for row in rows
    ]


def _brief_markdown(categories: list[dict]) -> str:
    lines = ["# Tradematic Market Brief", ""]
    for category in categories:
        lines.extend(
            [
                f"## {category['title']}",
                "",
                category["summary"].strip(),
                "",
                "Sources:",
            ]
        )
        for source in category["sources"]:
            title = source.get("title") or "Untitled"
            url = source.get("url") or ""
            lines.append(f"- {title} ({source.get('source', '')}) {url}".rstrip())
        lines.append("")
    return "\n".join(lines)


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


async def _analyze(args: argparse.Namespace) -> None:
    assets = load_assets(args.asset, Path(args.assets_file) if args.assets_file else None)
    result = await analyze_assets(
        Path(args.index),
        assets,
        Path(args.output_json),
        Path(args.output_md),
        args.model,
        args.ollama_url,
        args.top_k,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def _brief(args: argparse.Namespace) -> None:
    result = await brief_market(
        Path(args.index),
        Path(args.output_json),
        Path(args.output_md),
        args.model,
        args.ollama_url,
        args.top_k,
    )
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


def modelfile_main() -> None:
    parser = argparse.ArgumentParser(description="Write an Ollama Modelfile for Tradematic RAG analysis")
    parser.add_argument("--output", required=True)
    parser.add_argument("--base-model", default="llama3.1")
    args = parser.parse_args()
    print(json.dumps(write_modelfile(Path(args.output), args.base_model), ensure_ascii=False, indent=2))


def analyze_main() -> None:
    parser = argparse.ArgumentParser(description="Analyze assets with Ollama using CSV-backed RAG context")
    parser.add_argument("--index", required=True)
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--assets-file", help="Path to a file with one or many asset tickers per line")
    parser.add_argument("--model", default=DEFAULT_ANALYST_MODEL)
    parser.add_argument("--ollama-url")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()
    asyncio.run(_analyze(args))


def brief_main() -> None:
    parser = argparse.ArgumentParser(description="Generate categorized market brief with Ollama")
    parser.add_argument("--index", required=True)
    parser.add_argument("--model", default=DEFAULT_ANALYST_MODEL)
    parser.add_argument("--ollama-url")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()
    asyncio.run(_brief(args))
