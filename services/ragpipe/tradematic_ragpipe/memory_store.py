from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def save_event(path: Path, text: str, metadata: dict[str, Any]) -> None:
    data = load_memory(path)
    data.append(
        {
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "meta": metadata,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data[-5000:], file, ensure_ascii=False, indent=2)


def save_answer(path: Path, question: str, answer: str, matches: list[dict[str, Any]]) -> None:
    save_event(
        path,
        answer,
        {
            "kind": "answer",
            "question": question,
            "sources": [
                {
                    "title": match.get("title", ""),
                    "source": match.get("source", ""),
                    "url": match.get("url", ""),
                }
                for match in matches
            ],
        },
    )


def load_memory(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (json.JSONDecodeError, OSError):
        return []
    return payload if isinstance(payload, list) else []
