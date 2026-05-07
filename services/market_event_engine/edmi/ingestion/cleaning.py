import html
import re


HTML_TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
TECHNICAL_PAGE_MARKERS = (
    "enable javascript",
    "403 forbidden",
    "404 not found",
    "access denied",
    "captcha",
    "cookie policy",
    "privacy policy",
    "page not found",
    "регистрация пройдена успешно",
    "включите javascript",
    "доступ запрещен",
    "страница не найдена",
)


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = HTML_TAG_RE.sub(" ", value)
    return SPACE_RE.sub(" ", value).strip()


def is_noise(title: str, text: str) -> bool:
    if not clean_text(title):
        return True
    if len(clean_text(text)) < 35:
        return True
    cleaned = clean_text(f"{title} {text}")
    if len(cleaned) < 40:
        return True
    lower = cleaned.lower()
    if lower in {"n/a", "none", "null"} or lower.count("http") > 10:
        return True
    return any(marker in lower for marker in TECHNICAL_PAGE_MARKERS)
