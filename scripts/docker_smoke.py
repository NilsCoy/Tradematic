from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path


WEB_URL = "http://web:8001/"
EDMI_URL = "http://edmi-api:8000/health"
RAGPIPE_QUERY_URL = "http://edmi-api:8000/ragpipe/query"
RAGPIPE_INDEX_DIR = "/app/main/scripts/datasets/ragpipe"


def main() -> int:
    checks = [
        ("Django web", lambda: http_get(WEB_URL)),
        ("EDMI API", lambda: http_get(EDMI_URL)),
        ("news CSV", lambda: file_exists("services/news_aggregator/data/news_dataset.csv")),
        ("processed events", lambda: file_exists("main/scripts/datasets/processed_events.csv")),
        ("RAG index", lambda: file_exists("main/scripts/datasets/rag_index.csv")),
        ("ragpipe docs", lambda: file_exists("main/scripts/datasets/ragpipe/ragpipe_docs.jsonl")),
        ("ragpipe query", ragpipe_query),
    ]
    failed = []
    for name, check in checks:
        try:
            check()
            print(f"OK  {name}")
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERR {name}: {exc}")
            failed.append(name)
    return 1 if failed else 0


def http_get(url: str) -> str:
    return request(url)


def ragpipe_query() -> None:
    payload = {
        "question": "Какие новости важны для рынка?",
        "index_dir": RAGPIPE_INDEX_DIR,
        "top_k": 1,
    }
    response = request(
        RAGPIPE_QUERY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    parsed = json.loads(response)
    if not parsed.get("matches"):
        raise RuntimeError("no ragpipe matches returned")


def request(url: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> str:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or {})
            with urllib.request.urlopen(req, timeout=20) as response:
                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status}")
                return response.read().decode("utf-8", errors="replace")
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(last_error)


def file_exists(path: str) -> None:
    target = Path(path)
    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError(f"{path} is missing or empty")


if __name__ == "__main__":
    raise SystemExit(main())
