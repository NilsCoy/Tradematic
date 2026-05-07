import csv
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from edmi.config import Settings


@dataclass(frozen=True)
class PricePoint:
    timestamp: datetime
    price: float


class TradematicDatasetPriceProvider:
    def __init__(self, datasets_dir: Path | None) -> None:
        self.datasets_dir = datasets_dir
        self._cache: dict[Path, list[PricePoint]] = {}

    def price_delta(self, asset: str, at: datetime, horizon: str) -> float | None:
        for path in self._resolve_datasets(asset, horizon):
            points = self._read_points(path)
            if not points:
                continue

            start_time = _ensure_aware(at)
            end_time = start_time + _horizon_delta(horizon)
            start = self._point_at_or_before(points, start_time)
            end = self._point_at_or_before(points, end_time)
            if (
                start is None
                or end is None
                or end.timestamp <= start.timestamp
                or start.price == 0
            ):
                continue
            return (end.price - start.price) / start.price
        return None

    def latest_price(self, asset: str, horizon: str = "1d") -> float | None:
        latest: PricePoint | None = None
        for path in self._resolve_datasets(asset, horizon):
            points = self._read_points(path)
            if points and (latest is None or points[-1].timestamp > latest.timestamp):
                latest = points[-1]
        return latest.price if latest else None

    def coverage(self, asset: str) -> list[dict]:
        result = []
        seen: set[Path] = set()
        for horizon in ("1h", "1d"):
            for path in self._resolve_datasets(asset, horizon):
                if path in seen:
                    continue
                seen.add(path)
                points = self._read_points(path)
                if not points:
                    continue
                result.append(
                    {
                        "path": str(path),
                        "from": points[0].timestamp,
                        "to": points[-1].timestamp,
                        "points": len(points),
                    }
                )
        return result

    def _resolve_datasets(self, asset: str, horizon: str) -> list[Path]:
        if self.datasets_dir is None:
            return []
        datasets_dir = self.datasets_dir.expanduser()
        if not datasets_dir.is_absolute():
            datasets_dir = (Path.cwd() / datasets_dir).resolve()
        if not datasets_dir.exists():
            return []

        interval = _interval_name(horizon)
        normalized_asset = _normalize_asset(asset)
        candidates = [
            datasets_dir / f"{normalized_asset}_{interval}_data.csv",
            datasets_dir / f"{normalized_asset}_{interval}.csv",
            datasets_dir / f"{normalized_asset}.csv",
            datasets_dir / f"{interval}_data.csv",
        ]
        if interval == "daily":
            candidates.append(datasets_dir / "stock_data.csv")

        return [candidate for candidate in candidates if candidate.exists()]

    def _read_points(self, path: Path) -> list[PricePoint]:
        if path in self._cache:
            return self._cache[path]

        points: list[PricePoint] = []
        with path.open("r", encoding="cp1251", newline="") as file:
            reader = csv.reader(file)
            next(reader, None)
            for row in reader:
                if len(row) < 2:
                    continue
                try:
                    points.append(
                        PricePoint(
                            timestamp=_parse_timestamp(row[0]),
                            price=float(row[1].replace(",", ".")),
                        )
                    )
                except (TypeError, ValueError):
                    continue

        points.sort(key=lambda point: point.timestamp)
        self._cache[path] = points
        return points

    @staticmethod
    def _point_at_or_before(points: list[PricePoint], at: datetime) -> PricePoint | None:
        timestamps = [point.timestamp for point in points]
        index = bisect_right(timestamps, at) - 1
        if index < 0:
            return None
        return points[index]


class MarketDataService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tradematic = TradematicDatasetPriceProvider(settings.tradematic_datasets_dir)

    async def price_delta(self, asset: str, at: datetime, horizon: str) -> float | None:
        dataset_delta = self.tradematic.price_delta(asset, at, horizon)
        if dataset_delta is not None:
            return dataset_delta

        if not self.settings.tbank_token:
            return None

        # Placeholder for T-bank Invest API integration. The public contract stays
        # small so the pipeline does not depend on a vendor-specific response shape.
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService/FindInstrument",
                headers={"Authorization": f"Bearer {self.settings.tbank_token}"},
                params={"query": asset},
            )
            response.raise_for_status()
        return None

    async def latest_price(self, asset: str, horizon: str = "1d") -> float | None:
        return self.tradematic.latest_price(asset, horizon)

    async def coverage(self, asset: str) -> list[dict]:
        return self.tradematic.coverage(asset)


def _parse_timestamp(value: str) -> datetime:
    return _ensure_aware(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _horizon_delta(horizon: str) -> timedelta:
    normalized = horizon.lower()
    if normalized in {"1h", "hour", "hourly"}:
        return timedelta(hours=1)
    if normalized in {"1d", "day", "daily"}:
        return timedelta(days=1)
    raise ValueError(f"Unsupported market data horizon: {horizon}")


def _interval_name(horizon: str) -> str:
    normalized = horizon.lower()
    if normalized in {"1h", "hour", "hourly"}:
        return "hourly"
    if normalized in {"1d", "day", "daily"}:
        return "daily"
    return normalized


def _normalize_asset(asset: str) -> str:
    return "".join(char.lower() for char in asset if char.isalnum() or char in {"_", "-"})
