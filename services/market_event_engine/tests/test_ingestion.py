from pathlib import Path

from edmi.ingestion.csv_stream import iter_raw_news


def test_iter_raw_news_streams_valid_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "news.csv"
    csv_path.write_text(
        "source,title,text,url,chunks,loaded_at,published_at\n"
        "rss,Big Oil News,Brent oil rose after supply disruption,"
        "https://example.com/a,,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )

    rows = list(iter_raw_news(csv_path))

    assert len(rows) == 1
    assert rows[0].source == "rss"


def test_iter_raw_news_uses_loaded_at_when_published_at_is_empty(tmp_path: Path) -> None:
    csv_path = tmp_path / "news.csv"
    csv_path.write_text(
        "source,title,text,url,chunks,loaded_at,published_at\n"
        "rss,Big Oil News,Brent oil rose after supply disruption and the market reacted,"
        "https://example.com/a,,2026-01-01T00:00:00Z,\n",
        encoding="utf-8",
    )

    rows = list(iter_raw_news(csv_path))

    assert len(rows) == 1
    assert rows[0].published_at.isoformat() == "2026-01-01T00:00:00+00:00"


def test_iter_raw_news_allows_large_parser_fields(tmp_path: Path) -> None:
    csv_path = tmp_path / "news.csv"
    text = "Brent oil supply disruption " * 7000
    csv_path.write_text(
        "source,title,text,url,chunks,loaded_at,published_at\n"
        f"rss,Big Oil News,{text},https://example.com/a,,"
        "2026-01-01T00:00:00Z,2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )

    rows = list(iter_raw_news(csv_path))

    assert len(rows) == 1
    assert len(rows[0].text) > 131_072


def test_iter_raw_news_can_read_newest_first(tmp_path: Path) -> None:
    csv_path = tmp_path / "news.csv"
    csv_path.write_text(
        "source,title,text,url,chunks,loaded_at,published_at\n"
        "rss,Older News,Brent oil supply disruption moved markets,"
        "https://example.com/old,,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z\n"
        "rss,Newer News,Brent oil supply disruption moved markets again,"
        "https://example.com/new,,2026-01-02T00:00:00Z,2026-01-02T00:00:00Z\n",
        encoding="utf-8",
    )

    rows = list(iter_raw_news(csv_path, newest_first=True))

    assert [row.title for row in rows] == ["Newer News", "Older News"]
