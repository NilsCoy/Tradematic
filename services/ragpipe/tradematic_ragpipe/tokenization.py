from __future__ import annotations

import re


STOPWORDS = {
    "а",
    "в",
    "и",
    "или",
    "как",
    "какой",
    "какая",
    "какие",
    "на",
    "не",
    "о",
    "об",
    "по",
    "с",
    "что",
    "это",
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "to",
    "for",
}


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[\w.%-]+", text.lower())
        if token not in STOPWORDS and len(token) > 1
    ]
