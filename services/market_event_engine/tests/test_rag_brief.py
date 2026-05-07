from edmi.rag.csv_rag import _category_rows, _latest_rows


def test_category_rows_prefers_matching_event_types() -> None:
    rows = [
        {"title": "A", "event_type": "macro", "published_at": "2026-01-02T00:00:00+00:00"},
        {"title": "B", "event_type": "earnings", "published_at": "2026-01-01T00:00:00+00:00"},
    ]

    selected = _category_rows(rows, ("macro",), top_k=5)

    assert [row["title"] for row in selected] == ["A"]


def test_category_rows_falls_back_to_latest_rows_when_category_is_empty() -> None:
    rows = [
        {"title": "A", "event_type": "macro", "published_at": "2026-01-02T00:00:00+00:00"},
        {"title": "B", "event_type": "earnings", "published_at": "2026-01-01T00:00:00+00:00"},
    ]

    selected = _category_rows(rows, ("geopolitics",), top_k=1)

    assert [row["title"] for row in selected] == ["A"]


def test_latest_rows_sorts_by_publication_time_descending() -> None:
    rows = [
        {"title": "Older", "published_at": "2026-01-01T00:00:00+00:00"},
        {"title": "Newer", "published_at": "2026-01-02T00:00:00+00:00"},
    ]

    sorted_rows = _latest_rows(rows)

    assert [row["title"] for row in sorted_rows] == ["Newer", "Older"]
