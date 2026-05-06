from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from httpx import AsyncClient

from app.chunking import split_text_to_chunks
from app.config import ARTICLE_FETCH_CONCURRENCY, MIN_ARTICLE_WORDS, NEWS_SOURCES
from app.logging import logger
from app.models import NewsRecord
from app.sources.base import SourceCollector, SourceResult
from app.translation import translator


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "")
    return value.strip()


def normalize_text_lines(text: str) -> list[str]:
    return [clean_text(line) for line in text.splitlines() if clean_text(line)]


def word_count(value: str) -> int:
    return len(value.split())


def parse_datetime(raw_value: str | None) -> str:
    if not raw_value:
        return ""

    value = raw_value.strip()
    if not value:
        return ""

    for candidate in (value, value.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC).isoformat()
        except ValueError:
            pass

    try:
        parsed = parsedate_to_datetime(value)
        return parsed.astimezone(UTC).isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def html_to_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def format_exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return f"{type(exc).__name__}: {exc!r}"


@dataclass(slots=True)
class SourceDefinition:
    name: str
    section_url: str
    allowed_domains: tuple[str, ...]
    rss_url: str = ""
    min_article_words: int = MIN_ARTICLE_WORDS
    allow_rss_content_fallback: bool = False
    language: str = "ru"
    translate_to_russian: bool = False


@dataclass(slots=True)
class ArticleCandidate:
    url: str
    title: str = ""
    summary: str = ""
    published_at: str = ""


class HtmlNewsCollector(SourceCollector):
    def __init__(self, source: SourceDefinition) -> None:
        self.source = source
        self.source_name = source.name
        self.logger = logger.bind(
            component="news_source",
            source=self.source_name,
            section_url=self.source.section_url,
        )

    async def collect(self, client: AsyncClient) -> SourceResult:
        records: list[NewsRecord] = []
        errors: list[str] = []
        self.logger.bind(mode="collect").info("Starting source collection")
        async for event in self.stream_collect(client):
            if event["event"] == "record":
                records.append(event["record"])
            elif event["event"] == "error":
                errors.append(event["message"])
        self.logger.bind(records=len(records), errors=len(errors)).info(
            "Source collection finished"
        )
        return SourceResult(source=self.source_name, records=records, errors=errors)

    async def stream_collect(self, client: AsyncClient) -> AsyncIterator[dict]:
        try:
            article_candidates = await self._extract_article_candidates(client)
            self.logger.bind(urls_found=len(article_candidates)).info("Section parsed successfully")
            yield {
                "event": "info",
                "message": f"Найдено ссылок: {len(article_candidates)}",
                "source": self.source_name,
            }
        except Exception as exc:
            error_message = format_exception_message(exc)
            self.logger.exception("Failed to load source section")
            yield {
                "event": "error",
                "message": f"Не удалось загрузить раздел: {error_message}",
                "source": self.source_name,
            }
            return

        semaphore = asyncio.Semaphore(ARTICLE_FETCH_CONCURRENCY)
        tasks = [
            asyncio.create_task(self._parse_candidate_safely(client, candidate, semaphore))
            for candidate in article_candidates
        ]

        for task in asyncio.as_completed(tasks):
            event = await task
            if event is None:
                continue
            yield event

    async def _parse_candidate_safely(
        self,
        client: AsyncClient,
        candidate: ArticleCandidate,
        semaphore: asyncio.Semaphore,
    ) -> dict | None:
        article_logger = self.logger.bind(article_url=candidate.url)
        async with semaphore:
            try:
                record = await self._parse_article(client, candidate)
            except Exception as exc:
                error_message = format_exception_message(exc)
                article_logger.exception("Failed to parse article")
                return {
                    "event": "error",
                    "message": f"Ошибка статьи {candidate.url}: {error_message}",
                    "source": self.source_name,
                }

        if record is None:
            article_logger.debug("Article skipped after validation")
            return None

        article_logger.bind(title=record.title).info("Article parsed successfully")
        return {
            "event": "record",
            "record": record,
            "source": self.source_name,
            "message": f"Добавлена статья: {record.title}",
        }

    async def _extract_article_candidates(self, client: AsyncClient) -> list[ArticleCandidate]:
        if self.source.rss_url:
            return await self._extract_article_candidates_from_rss(client)

        self.logger.debug("Requesting section page")
        response = await client.get(self.source.section_url)
        response.raise_for_status()
        soup = html_to_soup(response.text)
        candidates: list[ArticleCandidate] = []
        seen: set[str] = set()

        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            absolute_url = urljoin(self.source.section_url, href)
            parsed = urlparse(absolute_url)
            if parsed.netloc not in self.source.allowed_domains:
                continue
            if not self._looks_like_article_url(absolute_url):
                continue
            normalized = absolute_url.split("#", 1)[0]
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(ArticleCandidate(url=normalized))

        self.logger.bind(urls_found=len(candidates)).debug("Article URLs extracted")
        return candidates[:20]

    async def _extract_article_candidates_from_rss(
        self, client: AsyncClient
    ) -> list[ArticleCandidate]:
        rss_logger = self.logger.bind(rss_url=self.source.rss_url)
        rss_logger.debug("Requesting RSS feed for article discovery")
        response = await client.get(self.source.rss_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "xml")
        if not soup.find_all(["item", "entry"]):
            rss_logger.bind(response_preview=response.text[:300]).warning(
                "RSS feed returned no items"
            )
        candidates: list[ArticleCandidate] = []
        seen: set[str] = set()

        for item in soup.find_all(["item", "entry"]):
            link = self._extract_link_from_feed_item(item)
            if not link:
                continue
            absolute_url = urljoin(self.source.section_url, link)
            parsed = urlparse(absolute_url)
            if parsed.netloc not in self.source.allowed_domains:
                continue
            if not self._looks_like_article_url(absolute_url):
                continue
            normalized = absolute_url.split("#", 1)[0]
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(
                ArticleCandidate(
                    url=normalized,
                    title=self._extract_feed_text(item, "title"),
                    summary=self._extract_feed_summary(item),
                    published_at=self._extract_feed_published_at(item),
                )
            )

        rss_logger.bind(urls_found=len(candidates)).debug("Article URLs extracted from RSS")
        return candidates[:20]

    def _extract_link_from_feed_item(self, item: BeautifulSoup) -> str:
        link_tag = item.find("link")
        if link_tag is None:
            return ""

        if link_tag.get("href"):
            return clean_text(link_tag.get("href", ""))
        return clean_text(link_tag.get_text(" ", strip=True))

    def _extract_feed_text(self, item: BeautifulSoup, tag_name: str) -> str:
        tag = item.find(tag_name)
        if tag is None:
            return ""
        return clean_text(tag.get_text(" ", strip=True))

    def _extract_feed_summary(self, item: BeautifulSoup) -> str:
        for tag_name in ("description", "summary", "content"):
            tag = item.find(tag_name)
            if tag is None:
                continue
            raw = tag.get_text(" ", strip=True)
            cleaned = clean_text(BeautifulSoup(raw, "html.parser").get_text(" ", strip=True))
            if cleaned:
                return cleaned
        return ""

    def _extract_feed_published_at(self, item: BeautifulSoup) -> str:
        for tag_name in ("pubDate", "published", "updated"):
            parsed = parse_datetime(self._extract_feed_text(item, tag_name))
            if parsed:
                return parsed
        return ""

    def _looks_like_article_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        if not path:
            return False

        if self.source_name == "Коммерсантъ":
            return bool(re.search(r"/doc/\d+$", path))
        if self.source_name == "ТАСС":
            return bool(re.search(r"^/ekonomika/\d+$", path))
        if self.source_name == "Ведомости":
            return bool(re.search(r"/articles/\d{4}/\d{2}/\d{2}/", path))
        if self.source_name == "РБК":
            return len(path.split("/")) >= 4
        if "lenta.ru" in parsed.netloc:
            return bool(
                re.search(r"^/news/\d{4}/\d{2}/\d{2}/", path)
                or re.search(r"^/articles/\d{4}/\d{2}/\d{2}/", path)
            )
        if "mk.ru" in parsed.netloc:
            return bool(re.search(r"^/economics/\d{4}/\d{2}/\d{2}/", path))
        if "ria.ru" in parsed.netloc:
            return bool(
                re.search(r"^/(?:\d{8}|[a-z_]+)/\d+\.html$", path) or re.search(r"^/20\d{6}/", path)
            )
        if "quote.ru" in parsed.netloc:
            return bool(re.search(r"^/news/article/", path))
        if "bfm.ru" in parsed.netloc:
            return bool(re.search(r"^/news/\d+$", path))
        if "banki.ru" in parsed.netloc:
            return bool(re.search(r"^/news/lenta/", path) or re.search(r"^/news/daytheme/", path))
        if "frankmedia.ru" in parsed.netloc:
            return len(path.split("/")) >= 3
        if "eadaily.com" in parsed.netloc:
            return bool(re.search(r"^/ru/news/\d{4}/\d{2}/\d{2}/", path))
        if "vc.ru" in parsed.netloc:
            return bool(re.search(r"^/.+/\d+", path))
        if "belta.by" in parsed.netloc:
            return bool(re.search(r"^/economics/view/", path))
        if "sputnik." in parsed.netloc:
            return bool(re.search(r"^/\d{8}/", path))
        if "dw.com" in parsed.netloc:
            return bool(re.search(r"^/ru/.+/a-\d+$", path))
        if "gazeta.ru" in parsed.netloc:
            return bool(re.search(r"^/business/\d{4}/\d{2}/\d{2}/", path))
        if "forbes.ru" in parsed.netloc:
            return bool(re.search(r"^/.+/\d+$", path))
        if "euronews.com" in parsed.netloc:
            return bool(re.search(r"^/\d{4}/\d{2}/\d{2}/", path))
        if "sputnik.by" in parsed.netloc:
            return bool(re.search(r"^/\d{8}/", path))
        if "bbc." in parsed.netloc:
            return bool(
                re.search(r"^/(?:russian|news)/(?:business|world|articles|features|topics)/", path)
                or re.search(r"^/news/.+-\d+$", path)
                or re.search(r"^/russian/.+", path)
            )
        if "theguardian.com" in parsed.netloc:
            return bool(re.search(r"^/\w+/\d{4}/[a-z]{3}/\d{2}/", path))
        if "cnbc.com" in parsed.netloc:
            return bool(re.search(r"/\d{4}/\d{2}/\d{2}/.*\.html$", path))
        return True

    async def _parse_article(
        self, client: AsyncClient, candidate: ArticleCandidate
    ) -> NewsRecord | None:
        url = candidate.url
        article_logger = self.logger.bind(article_url=url)
        article_logger.debug("Requesting article page")
        response = await client.get(url)
        response.raise_for_status()
        soup = html_to_soup(response.text)

        title = self._extract_title(soup) or candidate.title
        extracted_text = self._extract_text(soup)
        text = extracted_text
        published_at = self._extract_published_at(soup) or candidate.published_at

        if not text and self.source.allow_rss_content_fallback and candidate.summary:
            text = candidate.summary
            article_logger.bind(summary_words=word_count(text)).warning(
                "Falling back to RSS summary as article text"
            )

        if not title or not text:
            article_logger.bind(has_title=bool(title), has_text=bool(text)).warning(
                "Article has no usable content and will be skipped"
            )
            return None

        if self.source.translate_to_russian:
            article_logger.info("Translating article content to Russian")
            title = translator.translate_text(title, self.source_name)
            text = translator.translate_text(text, self.source_name)

        words_total = word_count(text)
        if words_total < self.source.min_article_words:
            article_logger.bind(words_total=words_total).warning(
                "Article is shorter than allowed minimum"
            )
            return None

        loaded_at = datetime.now(UTC).isoformat()
        article_logger.bind(
            words_total=words_total,
            published_at=published_at,
            used_rss_fallback=bool(
                self.source.allow_rss_content_fallback and candidate.summary and not extracted_text
            ),
        ).debug("Article content extracted")
        return NewsRecord(
            source=self.source_name,
            title=title,
            text=text,
            url=url,
            chunks=split_text_to_chunks(text),
            loaded_at=loaded_at,
            published_at=published_at,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        selectors = [
            'meta[property="og:title"]',
            'meta[property="twitter:title"]',
            'meta[name="twitter:title"]',
            'meta[name="title"]',
            "h1",
            "title",
        ]
        for selector in selectors:
            tag = soup.select_one(selector)
            if not tag:
                continue
            content = tag.get("content") if tag.name == "meta" else tag.get_text(" ", strip=True)
            cleaned = clean_text(content or "")
            if cleaned:
                self.logger.bind(selector=selector, title=cleaned).debug("Title extracted")
                return cleaned

        json_ld_title = self._extract_title_from_json_ld(soup)
        if json_ld_title:
            self.logger.bind(title=json_ld_title).debug("Title extracted from JSON-LD")
            return json_ld_title

        text_title = self._extract_title_from_page_text(soup)
        if text_title:
            self.logger.bind(title=text_title).debug("Title extracted from page text fallback")
            return text_title

        self.logger.warning("Failed to extract title")
        return ""

    def _extract_text(self, soup: BeautifulSoup) -> str:
        candidates = [
            "article p",
            '[itemprop="articleBody"] p',
            ".article_text_wrapper p",
            ".article_text p",
            ".article__text p",
            ".doc__body p",
            ".tm-article-body p",
            ".box-paragraph p",
            ".article-content p",
            ".story__content p",
            '[data-module="ArticleBody"] p',
            '[class*="article-body"] p',
            '[class*="ArticleBody"] p',
            '[class*="story-body"] p',
            '[class*="Body"] p',
            ".news-item p",
            ".text-block p",
            "main p",
        ]
        paragraphs: list[str] = []
        for selector in candidates:
            found = [clean_text(p.get_text(" ", strip=True)) for p in soup.select(selector)]
            found = [item for item in found if item]
            if len(" ".join(found).split()) >= MIN_ARTICLE_WORDS:
                paragraphs = found
                self.logger.bind(selector=selector, paragraphs=len(paragraphs)).debug(
                    "Article text extracted from selector"
                )
                break
            if len(found) > len(paragraphs):
                paragraphs = found

        if not paragraphs:
            paragraphs = self._extract_text_from_json_ld(soup)
            if paragraphs:
                self.logger.bind(paragraphs=len(paragraphs)).debug(
                    "Article text extracted from JSON-LD"
                )

        if not paragraphs:
            paragraphs = self._extract_text_from_large_containers(soup)
            if paragraphs:
                self.logger.bind(paragraphs=len(paragraphs)).debug(
                    "Article text extracted from fallback containers"
                )

        if not paragraphs:
            paragraphs = self._extract_text_from_page_text(soup)
            if paragraphs:
                self.logger.bind(paragraphs=len(paragraphs)).debug(
                    "Article text extracted from page text fallback"
                )

        return clean_text("\n".join(paragraphs))

    def _extract_title_from_json_ld(self, soup: BeautifulSoup) -> str:
        for script in soup.select('script[type="application/ld+json"]'):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for item in self._iter_json_ld_items(data):
                for key in ("headline", "name"):
                    value = item.get(key)
                    if isinstance(value, str) and clean_text(value):
                        return clean_text(value)
        return ""

    def _extract_title_from_page_text(self, soup: BeautifulSoup) -> str:
        lines = normalize_text_lines(soup.get_text("\n", strip=True))
        blacklist = {
            "en",
            "поиск",
            "рубрики",
            "все новости",
            "редакция сайта тасс",
        }

        for line in lines[:80]:
            line_lower = line.lower()
            if line_lower in blacklist:
                continue
            if len(line.split()) < 4:
                continue
            if re.search(r"(©|/тасс/|^\d{1,2}:\d{2}$)", line_lower):
                continue
            return line
        return ""

    def _extract_text_from_json_ld(self, soup: BeautifulSoup) -> list[str]:
        paragraphs: list[str] = []
        for script in soup.select('script[type="application/ld+json"]'):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self.logger.bind(raw_preview=raw[:120]).debug("Skipping invalid JSON-LD block")
                continue

            for item in self._iter_json_ld_items(data):
                body = item.get("articleBody")
                if isinstance(body, str) and body.strip():
                    paragraphs.extend([clean_text(body)])
        return paragraphs

    def _iter_json_ld_items(self, data: object) -> list[dict]:
        if isinstance(data, dict):
            items = [data]
            graph = data.get("@graph")
            if isinstance(graph, list):
                items.extend(item for item in graph if isinstance(item, dict))
            return items
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def _extract_text_from_large_containers(self, soup: BeautifulSoup) -> list[str]:
        candidates = soup.select("article, main, section, div")
        best_paragraphs: list[str] = []
        best_words = 0

        for container in candidates:
            paragraphs = [
                clean_text(node.get_text(" ", strip=True)) for node in container.select("p, div")
            ]
            paragraphs = [item for item in paragraphs if len(item.split()) >= 12]
            words_total = len(" ".join(paragraphs).split())
            if words_total > best_words:
                best_words = words_total
                best_paragraphs = paragraphs

        return best_paragraphs

    def _extract_text_from_page_text(self, soup: BeautifulSoup) -> list[str]:
        lines = normalize_text_lines(soup.get_text("\n", strip=True))
        if not lines:
            return []

        skip_patterns = (
            r"^en$",
            r"^поиск$",
            r"^рубрики$",
            r"^все новости$",
            r"^главная",
            r"^редакция сайта тасс$",
            r"^версия для печати",
            r"^теги$",
        )

        filtered_lines: list[str] = []
        for line in lines:
            line_lower = line.lower()
            if any(re.search(pattern, line_lower) for pattern in skip_patterns):
                continue
            if "{{" in line or "}}" in line:
                continue
            if len(line.split()) < 6:
                continue
            filtered_lines.append(line)

        paragraphs: list[str] = []
        started = False
        for line in filtered_lines:
            if not started and re.search(r"/(?:тасс|итар-тасс)/\.", line.lower()):
                started = True

            if started:
                paragraphs.append(line)

        if not paragraphs:
            paragraphs = filtered_lines

        return paragraphs

    def _extract_published_at(self, soup: BeautifulSoup) -> str:
        selectors = [
            'meta[property="article:published_time"]',
            'meta[name="publication_date"]',
            'meta[itemprop="datePublished"]',
            'meta[property="og:published_time"]',
            "time[datetime]",
        ]

        for selector in selectors:
            tag = soup.select_one(selector)
            if not tag:
                continue
            if tag.name == "meta":
                raw_value = tag.get("content")
            else:
                raw_value = tag.get("datetime") or tag.get_text(" ", strip=True)
            parsed = parse_datetime(raw_value)
            if parsed:
                self.logger.bind(selector=selector, published_at=parsed).debug(
                    "Published date extracted"
                )
                return parsed

        for script in soup.select('script[type="application/ld+json"]'):
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for item in self._iter_json_ld_items(data):
                for key in ("datePublished", "dateCreated"):
                    parsed = parse_datetime(item.get(key))
                    if parsed:
                        self.logger.bind(published_at=parsed, key=key).debug(
                            "Published date extracted from JSON-LD"
                        )
                        return parsed
        self.logger.debug("Published date not found")
        return ""


def build_news_collectors() -> list[HtmlNewsCollector]:
    collectors = [
        HtmlNewsCollector(
            SourceDefinition(
                name=source["name"],
                section_url=source["section_url"],
                allowed_domains=source["allowed_domains"],
                rss_url=source.get("rss_url", ""),
                min_article_words=source.get("min_article_words", MIN_ARTICLE_WORDS),
                allow_rss_content_fallback=source.get("allow_rss_content_fallback", False),
                language=source.get("language", "ru"),
                translate_to_russian=source.get("translate_to_russian", False),
            )
        )
        for source in NEWS_SOURCES
    ]
    logger.bind(component="news_source_factory", collectors=len(collectors)).debug(
        "News collectors created"
    )
    return collectors
