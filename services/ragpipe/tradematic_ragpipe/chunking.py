from __future__ import annotations


def chunk_text(text: str, max_words: int = 180, overlap: int = 40) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(max_words - overlap, 1)
    chunks: list[str] = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + max_words]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks
