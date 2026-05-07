from datetime import datetime, timezone

import pytest

from edmi.config import Settings
from edmi.services.market_data import MarketDataService


@pytest.mark.asyncio
async def test_price_delta_uses_tradematic_hourly_dataset(tmp_path) -> None:
    dataset = tmp_path / "sber_hourly_data.csv"
    dataset.write_text(
        "Date,Price\n"
        "2026-01-01 10:00:00+00:00,100\n"
        "2026-01-01 11:00:00+00:00,110\n",
        encoding="cp1251",
    )
    service = MarketDataService(Settings(tradematic_datasets_dir=tmp_path))

    delta = await service.price_delta(
        "SBER",
        datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc),
        "1h",
    )

    assert delta == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_price_delta_returns_none_when_dataset_does_not_cover_horizon(tmp_path) -> None:
    dataset = tmp_path / "daily_data.csv"
    dataset.write_text(
        "Date,Price\n"
        "2026-01-01 00:00:00+00:00,100\n",
        encoding="cp1251",
    )
    service = MarketDataService(Settings(tradematic_datasets_dir=tmp_path))

    delta = await service.price_delta(
        "ANY",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        "1d",
    )

    assert delta is None


@pytest.mark.asyncio
async def test_price_delta_falls_back_to_stock_data_when_daily_misses_date(tmp_path) -> None:
    daily = tmp_path / "daily_data.csv"
    daily.write_text(
        "Date,Price\n"
        "2025-01-01 00:00:00+00:00,100\n",
        encoding="cp1251",
    )
    stock = tmp_path / "stock_data.csv"
    stock.write_text(
        "Date,Price\n"
        "2026-03-01 00:00:00+00:00,100\n"
        "2026-03-02 00:00:00+00:00,105\n",
        encoding="cp1251",
    )
    service = MarketDataService(Settings(tradematic_datasets_dir=tmp_path))

    delta = await service.price_delta(
        "ANY",
        datetime(2026, 3, 1, tzinfo=timezone.utc),
        "1d",
    )

    assert delta == pytest.approx(0.05)
