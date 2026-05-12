from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an Ollama model through the HTTP API")
    parser.add_argument("--model", required=True)
    parser.add_argument("--modelfile", required=True)
    parser.add_argument("--ollama-url", default=os.environ.get("EDMI_OLLAMA_URL", "http://localhost:11434"))
    args = parser.parse_args()

    modelfile = Path(args.modelfile)
    payload = _payload_from_modelfile(args.model, modelfile)
    url = args.ollama_url.rstrip("/") + "/api/create"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Failed to create Ollama model via {url}: HTTP {exc.code} {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Failed to create Ollama model via {url}: {exc}", file=sys.stderr)
        return 1

    if body:
        print(body)
    return 0


def _payload_from_modelfile(model: str, modelfile: Path) -> dict[str, str | bool]:
    text = modelfile.read_text(encoding="utf-8")
    base_model = "llama3.1"
    system = ""
    for line in text.splitlines():
        if line.startswith("FROM "):
            base_model = line.removeprefix("FROM ").strip()
            break
    marker = 'SYSTEM """'
    start = text.find(marker)
    if start >= 0:
        start += len(marker)
        end = text.find('"""', start)
        if end >= 0:
            system = text[start:end].strip()
    return {
        "model": model,
        "from": base_model,
        "system": system,
        "stream": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
