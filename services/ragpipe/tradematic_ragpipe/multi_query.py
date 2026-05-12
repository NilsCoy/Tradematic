from __future__ import annotations

import re

import httpx

from tradematic_ragpipe.settings import RagpipeSettings


async def generate_queries(question: str, settings: RagpipeSettings, count: int = 4) -> list[str]:
    prompt = f"""
Сгенерируй {count} альтернативных поисковых запроса для финансовой RAG-системы.
Запросы должны быть короткими, без пояснений, каждый с новой строки.

Вопрос: {question}
""".strip()
    try:
        async with httpx.AsyncClient(timeout=settings.multi_query_timeout) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={"model": settings.chat_model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            text = str(response.json().get("response", ""))
    except Exception:
        return [question]

    queries = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if cleaned and cleaned not in queries:
            queries.append(cleaned)
    if question not in queries:
        queries.append(question)
    return queries[: count + 1]
