from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "news_dataset.csv"

REQUEST_TIMEOUT = 30.0
ARTICLE_FETCH_CONCURRENCY = 8
SOURCE_FETCH_CONCURRENCY = 4
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

MIN_ARTICLE_WORDS = 300
TARGET_CHUNK_WORDS = 350
MIN_CHUNK_WORDS = 150
CHUNK_OVERLAP_WORDS = 50
CHUNK_SEPARATOR = " ||| "

CBR_SOURCE = "ЦБ РФ"
CBR_ROW_URL = "https://www.cbr-xml-daily.ru/"
CBR_ENDPOINTS = (
    {"url": "https://www.cbr-xml-daily.ru/daily_json.js", "format": "json"},
    {"url": "https://www.cbr-xml-daily.com/daily_json.js", "format": "json"},
    {"url": "https://www.cbr.ru/scripts/XML_daily.asp", "format": "xml"},
)
CBR_TARGET_CODES = (
    "USD",
    "EUR",
    "CNY",
    "BYN",
    "KZT",
    "GBP",
    "JPY",
    "CHF",
    "AED",
    "AMD",
    "AUD",
    "AZN",
    "BGN",
    "BRL",
    "CAD",
    "CZK",
    "DKK",
    "EGP",
    "GEL",
    "HKD",
    "HUF",
    "IDR",
    "INR",
    "KGS",
    "KRW",
    "MDL",
    "NOK",
    "NZD",
    "PLN",
    "QAR",
    "RON",
    "RSD",
    "SEK",
    "SGD",
    "TJS",
    "TMT",
    "TRY",
    "UAH",
    "UZS",
    "XDR",
    "ZAR",
)

NEWS_SOURCES = (
    {
        "name": "РБК",
        "section_url": "https://www.rbc.ru/finances/",
        "allowed_domains": ("www.rbc.ru", "rbc.ru"),
        "language": "ru",
    },
    {
        "name": "Коммерсантъ",
        "section_url": "https://www.kommersant.ru/",
        "allowed_domains": ("www.kommersant.ru", "kommersant.ru"),
        "language": "ru",
    },
    {
        "name": "ТАСС",
        "section_url": "https://tass.ru/ekonomika",
        "rss_url": "https://tass.ru/rss/v2.xml",
        "allowed_domains": ("tass.ru", "www.tass.ru"),
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
        "language": "ru",
    },
    {
        "name": "Ведомости",
        "section_url": "https://www.vedomosti.ru/finance",
        "allowed_domains": ("www.vedomosti.ru", "vedomosti.ru"),
        "language": "ru",
    },
    {
        "name": "Лента.ру Экономика",
        "section_url": "https://lenta.ru/rubrics/economics/",
        "rss_url": "https://lenta.ru/rss/news/economics",
        "allowed_domains": ("lenta.ru", "www.lenta.ru"),
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
        "language": "ru",
    },
    {
        "name": "Лента.ру Мир",
        "section_url": "https://lenta.ru/rubrics/world/",
        "rss_url": "https://lenta.ru/rss/news/world",
        "allowed_domains": ("lenta.ru", "www.lenta.ru"),
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
        "language": "ru",
    },
    {
        "name": "МК Экономика",
        "section_url": "https://www.mk.ru/economics/",
        "rss_url": "https://www.mk.ru/rss/economics/index.xml",
        "allowed_domains": ("www.mk.ru", "mk.ru"),
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
        "language": "ru",
    },
    {
        "name": "Газета.Ru Бизнес",
        "section_url": "https://www.gazeta.ru/business/",
        "allowed_domains": ("www.gazeta.ru", "gazeta.ru"),
        "language": "ru",
    },
    {
        "name": "Forbes Russia",
        "section_url": "https://www.forbes.ru/finansy",
        "allowed_domains": ("www.forbes.ru", "forbes.ru"),
        "language": "ru",
    },
    {
        "name": "Euronews RU Business",
        "section_url": "https://ru.euronews.com/business",
        "allowed_domains": ("ru.euronews.com", "euronews.com"),
        "language": "ru",
    },
    {
        "name": "BBC Russian",
        "section_url": "https://www.bbc.com/russian",
        "allowed_domains": ("www.bbc.com", "bbc.com", "www.bbc.co.uk", "bbc.co.uk"),
        "language": "ru",
    },
    {
        "name": "Sputnik Беларусь",
        "section_url": "https://sputnik.by/economy/",
        "allowed_domains": ("sputnik.by", "www.sputnik.by"),
        "language": "ru",
    },
    {
        "name": "РИА Новости Экономика",
        "section_url": "https://ria.ru/economy/",
        "allowed_domains": ("ria.ru", "www.ria.ru"),
        "language": "ru",
    },
    {
        "name": "РИА Новости Мир",
        "section_url": "https://ria.ru/world/",
        "allowed_domains": ("ria.ru", "www.ria.ru"),
        "language": "ru",
    },
    {
        "name": "РБК Инвестиции",
        "section_url": "https://quote.ru/",
        "allowed_domains": ("quote.ru", "www.quote.ru"),
        "language": "ru",
    },
    {
        "name": "BFM",
        "section_url": "https://www.bfm.ru/news",
        "allowed_domains": ("www.bfm.ru", "bfm.ru"),
        "language": "ru",
    },
    {
        "name": "Banki.ru",
        "section_url": "https://www.banki.ru/news/",
        "allowed_domains": ("www.banki.ru", "banki.ru"),
        "language": "ru",
    },
    {
        "name": "Frank Media",
        "section_url": "https://frankmedia.ru/",
        "allowed_domains": ("frankmedia.ru", "www.frankmedia.ru"),
        "language": "ru",
    },
    {
        "name": "EADaily",
        "section_url": "https://eadaily.com/ru/news/economics/",
        "allowed_domains": ("eadaily.com", "www.eadaily.com"),
        "language": "ru",
    },
    {
        "name": "VC.ru",
        "section_url": "https://vc.ru/",
        "allowed_domains": ("vc.ru", "www.vc.ru"),
        "language": "ru",
    },
    {
        "name": "БелТА Экономика",
        "section_url": "https://www.belta.by/economics/",
        "allowed_domains": ("www.belta.by", "belta.by"),
        "language": "ru",
    },
    {
        "name": "Sputnik Казахстан",
        "section_url": "https://sputnik.kz/economy/",
        "allowed_domains": ("sputnik.kz", "www.sputnik.kz"),
        "language": "ru",
    },
    {
        "name": "Sputnik Армения",
        "section_url": "https://sputnikarm.ru/economy/",
        "allowed_domains": ("sputnikarm.ru", "www.sputnikarm.ru"),
        "language": "ru",
    },
    {
        "name": "DW Russian",
        "section_url": "https://www.dw.com/ru/%D1%82%D0%B5%D0%BC%D1%8B/%D1%8D%D0%BA%D0%BE%D0%BD%D0%BE%D0%BC%D0%B8%D0%BA%D0%B0/s-10022",
        "allowed_domains": ("www.dw.com", "dw.com"),
        "language": "ru",
    },
    {
        "name": "BBC Business",
        "section_url": "https://www.bbc.com/news/business",
        "rss_url": "http://feeds.bbci.co.uk/news/business/rss.xml",
        "allowed_domains": ("www.bbc.com", "bbc.com", "www.bbc.co.uk", "bbc.co.uk"),
        "language": "en",
        "translate_to_russian": True,
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
    },
    {
        "name": "BBC World",
        "section_url": "https://www.bbc.com/news/world",
        "rss_url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "allowed_domains": ("www.bbc.com", "bbc.com", "www.bbc.co.uk", "bbc.co.uk"),
        "language": "en",
        "translate_to_russian": True,
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
    },
    {
        "name": "The Guardian World",
        "section_url": "https://www.theguardian.com/world",
        "rss_url": "https://www.theguardian.com/world/rss",
        "allowed_domains": ("www.theguardian.com", "theguardian.com"),
        "language": "en",
        "translate_to_russian": True,
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
    },
    {
        "name": "The Guardian Business",
        "section_url": "https://www.theguardian.com/business",
        "rss_url": "https://www.theguardian.com/business/rss",
        "allowed_domains": ("www.theguardian.com", "theguardian.com"),
        "language": "en",
        "translate_to_russian": True,
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
    },
    {
        "name": "CNBC News",
        "section_url": "https://www.cnbc.com/",
        "rss_url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "allowed_domains": ("www.cnbc.com", "cnbc.com"),
        "language": "en",
        "translate_to_russian": True,
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
    },
    {
        "name": "CNBC World",
        "section_url": "https://www.cnbc.com/world/",
        "rss_url": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
        "allowed_domains": ("www.cnbc.com", "cnbc.com"),
        "language": "en",
        "translate_to_russian": True,
        "min_article_words": 40,
        "allow_rss_content_fallback": True,
    },
)
