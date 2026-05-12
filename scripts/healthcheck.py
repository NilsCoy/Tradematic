from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: healthcheck.py http URL | file PATH [PATH...]")
        return 2
    mode = sys.argv[1]
    if mode == "http":
        return check_http(sys.argv[2])
    if mode == "file":
        return check_files(sys.argv[2:])
    print(f"unknown mode: {mode}")
    return 2


def check_http(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read(2048).decode("utf-8", errors="replace")
            if response.status >= 400:
                print(f"{url} returned HTTP {response.status}")
                return 1
            if body.startswith("{"):
                json.loads(body)
            print(f"ok {url}")
            return 0
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"failed {url}: {exc}")
        return 1


def check_files(paths: list[str]) -> int:
    missing = [path for path in paths if not Path(path).exists()]
    if missing:
        print("missing files: " + ", ".join(missing))
        return 1
    print("ok files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
