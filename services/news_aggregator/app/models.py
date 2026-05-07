from dataclasses import asdict, dataclass


@dataclass(slots=True)
class NewsRecord:
    source: str
    title: str
    text: str
    url: str
    chunks: str
    loaded_at: str
    published_at: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)
