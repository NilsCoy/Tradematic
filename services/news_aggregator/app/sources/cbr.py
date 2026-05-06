from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from httpx import AsyncClient

from app.chunking import split_text_to_chunks
from app.config import CBR_ENDPOINTS, CBR_ROW_URL, CBR_SOURCE, CBR_TARGET_CODES
from app.logging import logger
from app.models import NewsRecord
from app.sources.base import SourceCollector, SourceResult
from app.sources.news import format_exception_message


class CbrCurrencyCollector(SourceCollector):
    source_name = CBR_SOURCE

    async def collect(self, client: AsyncClient) -> SourceResult:
        collector_logger = logger.bind(component="cbr", source=self.source_name, mode="collect")
        records: list[NewsRecord] = []
        errors: list[str] = []
        async for event in self.stream_collect(client):
            if event["event"] == "record":
                records.append(event["record"])
            elif event["event"] == "error":
                errors.append(event["message"])
        collector_logger.bind(records=len(records), errors=len(errors)).info(
            "Currency collect finished"
        )
        return SourceResult(source=self.source_name, records=records, errors=errors)

    async def stream_collect(self, client: AsyncClient) -> AsyncIterator[dict]:
        payload: dict | None = None
        last_error_message = ""

        for endpoint in CBR_ENDPOINTS:
            endpoint_url = endpoint["url"]
            endpoint_format = endpoint["format"]
            collector_logger = logger.bind(
                component="cbr",
                source=self.source_name,
                url=endpoint_url,
                format=endpoint_format,
            )
            collector_logger.info("Requesting CBR currency feed")

            try:
                response = await client.get(endpoint_url)
                response.raise_for_status()
                payload = self._parse_payload(response.text, endpoint_format)
                collector_logger.info("CBR currency feed loaded successfully")
                break
            except Exception as exc:
                last_error_message = format_exception_message(exc)
                collector_logger.exception("Failed to fetch CBR currency feed")

        if payload is None:
            yield {
                "event": "error",
                "message": f"Не удалось получить курсы: {last_error_message}",
                "source": self.source_name,
            }
            return

        loaded_at = datetime.now(UTC).isoformat()
        published_at = self._parse_cbr_date(payload.get("Date", ""))
        valute = payload.get("Valute", {})
        logger.bind(
            component="cbr",
            source=self.source_name,
            loaded_at=loaded_at,
            published_at=published_at,
        ).debug("CBR payload parsed")

        for code in CBR_TARGET_CODES:
            item = valute.get(code)
            if not item:
                logger.bind(component="cbr", source=self.source_name, currency_code=code).warning(
                    "Currency missing in CBR payload"
                )
                continue
            value = item["Value"]
            title = f"{item['Name']} = {value}"
            text = f"{item['Name']} курс {value} рублей"
            currency_logger = logger.bind(
                component="cbr",
                source=self.source_name,
                currency_code=code,
                value=value,
                title=title,
            )
            record = NewsRecord(
                source=self.source_name,
                title=title,
                text=text,
                url=CBR_ROW_URL,
                chunks=split_text_to_chunks(text),
                loaded_at=loaded_at,
                published_at=published_at,
            )
            currency_logger.debug("Prepared currency record")
            yield {
                "event": "record",
                "record": record,
                "source": self.source_name,
                "message": f"Обновлен курс: {title}",
            }

    def _parse_payload(self, raw_text: str, payload_format: str) -> dict:
        if payload_format == "json":
            return json.loads(raw_text)
        if payload_format == "xml":
            return self._parse_xml_payload(raw_text)
        raise ValueError(f"Unsupported payload format: {payload_format}")

    def _parse_xml_payload(self, raw_text: str) -> dict:
        root = ET.fromstring(raw_text)
        date_value = root.attrib.get("Date", "")
        valute: dict[str, dict] = {}

        for node in root.findall("Valute"):
            char_code = (node.findtext("CharCode") or "").strip()
            if char_code not in CBR_TARGET_CODES:
                continue

            nominal_raw = (node.findtext("Nominal") or "1").strip()
            value_raw = (node.findtext("Value") or "0").strip().replace(",", ".")
            try:
                nominal = float(nominal_raw)
                value = float(value_raw)
            except ValueError:
                continue
            normalized_value = value / nominal if nominal else value
            valute[char_code] = {
                "Name": (node.findtext("Name") or char_code).strip(),
                "Value": round(normalized_value, 6),
            }

        return {"Date": date_value, "Valute": valute}

    def _parse_cbr_date(self, value: str) -> str:
        date_logger = logger.bind(component="cbr", source=self.source_name, raw_date=value)
        if not value:
            date_logger.debug("Empty CBR date received")
            return ""
        try:
            if len(value) == 10 and value.count("/") == 2:
                parsed = datetime.strptime(value, "%d/%m/%Y").replace(tzinfo=UTC).isoformat()
                date_logger.bind(parsed_date=parsed).debug("Parsed CBR XML date")
                return parsed
            parsed = (
                datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).isoformat()
            )
            date_logger.bind(parsed_date=parsed).debug("Parsed CBR date")
            return parsed
        except ValueError:
            date_logger.exception("Failed to parse CBR date")
            return ""
