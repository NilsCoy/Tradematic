import re

from edmi.domain.models import Entities


COMPANY_RE = re.compile(r"\b(?:[A-ZА-Я][\w&.-]+(?:\s+[A-ZА-Я][\w&.-]+){0,3})\b")
COMMODITIES = {
    "oil": "oil",
    "brent": "oil",
    "gas": "gas",
    "gold": "gold",
    "copper": "copper",
    "нефть": "oil",
    "газ": "gas",
    "золото": "gold",
}
MACRO = {
    "inflation": "inflation",
    "rate": "interest_rate",
    "gdp": "gdp",
    "cpi": "inflation",
    "инфляц": "inflation",
    "ставк": "interest_rate",
    "ввп": "gdp",
}


class NERService:
    def __init__(self) -> None:
        self._natasha_ready = False
        self._natasha = None

    async def extract(self, text: str) -> Entities:
        natasha_entities = self._extract_with_natasha(text)
        fallback_entities = self._extract_with_rules(text)
        return Entities(
            companies=sorted(set(natasha_entities.companies + fallback_entities.companies)),
            commodities=sorted(set(fallback_entities.commodities)),
            macro=sorted(set(fallback_entities.macro)),
        )

    def _extract_with_natasha(self, text: str) -> Entities:
        if self._natasha is None and not self._natasha_ready:
            self._natasha_ready = True
            try:
                from natasha import Doc, MorphVocab, NewsEmbedding, NewsNERTagger, Segmenter
            except ImportError:
                return Entities()
            emb = NewsEmbedding()
            self._natasha = (Doc, Segmenter(), NewsNERTagger(emb), MorphVocab())

        if self._natasha is None:
            return Entities()

        Doc, segmenter, ner_tagger, _ = self._natasha
        doc = Doc(text)
        doc.segment(segmenter)
        doc.tag_ner(ner_tagger)
        companies = [span.text for span in doc.spans if span.type == "ORG"]
        return Entities(companies=companies)

    @staticmethod
    def _extract_with_rules(text: str) -> Entities:
        lower = text.lower()
        commodities = [label for token, label in COMMODITIES.items() if token in lower]
        macro = [label for token, label in MACRO.items() if token in lower]
        companies = [
            match.group(0).strip()
            for match in COMPANY_RE.finditer(text)
            if len(match.group(0).strip()) > 2
        ][:20]
        return Entities(companies=companies, commodities=commodities, macro=macro)

