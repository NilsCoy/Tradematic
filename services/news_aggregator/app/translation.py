from __future__ import annotations

from app.logging import logger

try:
    from deep_translator import GoogleTranslator
except ImportError:  # pragma: no cover
    GoogleTranslator = None


class TranslationService:
    def __init__(self, target_language: str = "ru", max_chars: int = 3500) -> None:
        self.target_language = target_language
        self.max_chars = max_chars
        self.logger = logger.bind(component="translation", target_language=target_language)

    def translate_text(self, text: str, source_label: str) -> str:
        translation_logger = self.logger.bind(source=source_label)
        if not text.strip():
            return text
        if GoogleTranslator is None:
            translation_logger.warning("deep-translator is not installed, translation skipped")
            return text

        chunks = self._split_text(text)
        translated_chunks: list[str] = []
        translator = GoogleTranslator(source="auto", target=self.target_language)

        for index, chunk in enumerate(chunks, start=1):
            try:
                translated = translator.translate(chunk)
            except Exception as exc:  # pragma: no cover
                translation_logger.bind(chunk_index=index).warning(
                    f"Translation failed, original text kept: {type(exc).__name__}: {exc}"
                )
                translated = chunk
            translated_chunks.append(translated)

        translation_logger.bind(chunks_total=len(chunks)).debug("Translation completed")
        return "\n".join(translated_chunks).strip()

    def _split_text(self, text: str) -> list[str]:
        paragraphs = [paragraph.strip() for paragraph in text.split("\n") if paragraph.strip()]
        if not paragraphs:
            return [text]

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= self.max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = paragraph
        if current:
            chunks.append(current)
        return chunks or [text]


translator = TranslationService()
