from app.config import (
    CHUNK_OVERLAP_WORDS,
    CHUNK_SEPARATOR,
    MIN_CHUNK_WORDS,
    TARGET_CHUNK_WORDS,
)
from app.logging import logger


def split_text_to_chunks(text: str) -> str:
    words = text.split()
    chunk_logger = logger.bind(component="chunking", words_total=len(words))

    if not words:
        chunk_logger.debug("Empty text received for chunking")
        return ""

    if len(words) <= TARGET_CHUNK_WORDS:
        chunk_logger.debug("Text is short enough, returning a single chunk")
        return text.strip()

    step = TARGET_CHUNK_WORDS - CHUNK_OVERLAP_WORDS
    chunks: list[str] = []
    start = 0

    while start < len(words):
        end = min(start + TARGET_CHUNK_WORDS, len(words))
        chunk_words = words[start:end]

        if len(chunk_words) < MIN_CHUNK_WORDS and chunks:
            previous = chunks.pop()
            merged = f"{previous} {' '.join(chunk_words)}".strip()
            chunks.append(merged)
            break

        chunks.append(" ".join(chunk_words).strip())
        if end == len(words):
            break
        start += step

    chunk_logger.bind(chunks_total=len(chunks)).debug("Chunking completed")
    return CHUNK_SEPARATOR.join(chunk for chunk in chunks if chunk)
