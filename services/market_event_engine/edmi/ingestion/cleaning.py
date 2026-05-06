import html
import re


HTML_TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = HTML_TAG_RE.sub(" ", value)
    return SPACE_RE.sub(" ", value).strip()


def is_noise(title: str, text: str) -> bool:
    cleaned = clean_text(f"{title} {text}")
    if len(cleaned) < 40:
        return True
    lower = cleaned.lower()
    return lower in {"n/a", "none", "null"} or lower.count("http") > 10

