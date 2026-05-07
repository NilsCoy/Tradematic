from edmi.infrastructure.dedup import news_hash


def test_news_hash_uses_url_and_text() -> None:
    text = "Central bank raised interest rates and markets reacted."

    assert news_hash("https://example.com/a", text) != news_hash("https://example.com/b", text)
