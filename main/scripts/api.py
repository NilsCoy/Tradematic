import csv
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import grpc
import matplotlib.pyplot as plt
import tinkoff.invest as ti
from tinkoff.invest import InstrumentIdType
from tqdm import tqdm
import pandas as pd
import numpy as np


# Инициализация клиента
def get_client(token):
    """Получает клинета по токену"""
    with ti.Client(token) as client:
        try:
            return ti.Client(token)
        except grpc.RpcError as e:
            print(f"Ошибка получения данных: {e.details()}")


# Получение исторических данных
def get_hourly_data(client, figi, hours=24, max_chunk_hours=600):
    """Почасовая история"""
    now = datetime.now()
    all_candles = []

    for i in tqdm(range(0, hours, max_chunk_hours), desc='Загрузка часовых данных'):
        chunk_hours = min(max_chunk_hours, hours - i)
        from_time = now - timedelta(hours=i + chunk_hours)
        to_time = now - timedelta(hours=i)

        candles = client.market_data.get_candles(
            figi=figi, from_=from_time, to=to_time, interval=ti.CandleInterval.CANDLE_INTERVAL_HOUR
        )
        all_candles.extend(candles.candles)

    return all_candles


def get_daily_data(client, figi, days=365, max_chunk_days=365):
    """Дневная история"""
    now = datetime.now()
    all_candles = []

    for i in tqdm(range(0, days, max_chunk_days), desc='Загрузка дневных данных'):
        chunk_days = min(max_chunk_days, days - i)
        from_time = now - timedelta(days=i + chunk_days)
        to_time = now - timedelta(days=i)

        candles = client.market_data.get_candles(
            figi=figi, from_=from_time, to=to_time, interval=ti.CandleInterval.CANDLE_INTERVAL_DAY
        )
        all_candles.extend(candles.candles)

    return all_candles


def get_weekly_data(client, figi, weeks=52, max_chunk_weeks=104):
    """Недельная история"""
    now = datetime.now()
    all_candles = []

    for i in tqdm(range(0, weeks, max_chunk_weeks), desc='Загрузка недельных данных'):
        chunk_weeks = min(max_chunk_weeks, weeks - i)
        from_time = now - timedelta(weeks=i + chunk_weeks)
        to_time = now - timedelta(weeks=i)

        candles = client.market_data.get_candles(
            figi=figi, from_=from_time, to=to_time, interval=ti.CandleInterval.CANDLE_INTERVAL_WEEK
        )
        all_candles.extend(candles.candles)

    return all_candles


def get_monthly_data(client, figi, months=60, max_chunk_months=24):
    """Месячная история"""
    now = datetime.now()
    all_candles = []

    for i in tqdm(range(0, months, max_chunk_months), desc='Загрузка месячных данных'):
        chunk_months = min(max_chunk_months, months - i)
        from_time = now - timedelta(days=30 * (i + chunk_months))  # Приблизительно
        to_time = now - timedelta(days=30 * i)

        candles = client.market_data.get_candles(
            figi=figi, from_=from_time, to=to_time, interval=ti.CandleInterval.CANDLE_INTERVAL_MONTH
        )
        all_candles.extend(candles.candles)

    return all_candles


def save_to_csv(candles, filename='stock_data.csv'):
    """Сохраняет данные в csv файл."""
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Дата', 'Цена'])
        for candle in candles:
            price = float(candle.close.units) + candle.close.nano / 1e9
            writer.writerow([candle.time, price])
    print(f'Данные сохранены в {filename}')


def plot_stock_price(candles):
    """Для теста, строит график."""
    dates = [candle.time for candle in candles]
    prices = [float(candle.close.units) + candle.close.nano / 1e9 for candle in candles]

    plt.figure(figsize=(10, 5))
    plt.plot(dates, prices, label='Цена акции')
    plt.xlabel('Дата')
    plt.ylabel('Цена')
    plt.title('График изменения цены акции')
    plt.legend()
    plt.grid()
    plt.show()


def get_account(token):
    """Получает портфель."""
    with get_client(token) as client:
        user_info = client.users.get_accounts()
        return user_info


def get_elements_in_portfolio(token):
    """Получает данные по списку портфеля."""
    with get_client(token) as client:
        portfolio = client.operations.get_portfolio(
            account_id=get_account(token).accounts[0].id
        )

        result = []

        for position in portfolio.positions:
            quantity = (
                position.quantity.units +
                position.quantity.nano / 1e9
            )

            avg_price = (
                position.average_position_price.units +
                position.average_position_price.nano / 1e9
            )

            cur_price = (
                position.current_price.units +
                position.current_price.nano / 1e9
            )

            item = {
                "name": get_name_stock(token, position.figi),
                "figi": position.figi,
                "quantity": quantity,
                "avg_price": avg_price,
                "cur_price": cur_price,
                "instrument_type": position.instrument_type,
                "metrics": calculate_metrics(position)
            }

            result.append(item)

        return result


def get_name_stock(token, figi):
    """Получает название инструмента по FIGI"""
    with get_client(token) as client:
        instrument = client.instruments.get_instrument_by(id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi)
        if instrument.instrument:
            return instrument.instrument.name
    return None

def candles_to_df(candles):
    df = pd.DataFrame([{
        "time": c.time,
        "open": float(c.open.units + c.open.nano / 1e9),
        "high": float(c.high.units + c.high.nano / 1e9),
        "low": float(c.low.units + c.low.nano / 1e9),
        "close": float(c.close.units + c.close.nano / 1e9),
        "volume": c.volume
    } for c in candles])

    df = df.sort_values("time", ascending=False)
    df.reset_index(drop=True, inplace=True)
    return df

def add_features(df):
    # ===== RETURNS =====
    df["return"] = df["close"].pct_change()
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))

    # ===== PRICE FEATURES =====
    df["range"] = df["high"] - df["low"]
    df["body"] = df["close"] - df["open"]

    df["upper_shadow"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_shadow"] = df[["open", "close"]].min(axis=1) - df["low"]

    # ===== MOVING AVERAGES =====
    df["sma_10"] = df["close"].rolling(10).mean()
    df["sma_20"] = df["close"].rolling(20).mean()

    df["ema_12"] = df["close"].ewm(span=12).mean()
    df["ema_26"] = df["close"].ewm(span=26).mean()

    # ===== MACD =====
    df["macd"] = df["ema_12"] - df["ema_26"]

    # ===== RSI =====
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # ===== BOLLINGER BANDS =====
    rolling_mean = df["close"].rolling(20).mean()
    rolling_std = df["close"].rolling(20).std()

    df["bb_upper"] = rolling_mean + 2 * rolling_std
    df["bb_lower"] = rolling_mean - 2 * rolling_std
    df["bb_width"] = df["bb_upper"] - df["bb_lower"]

    # ===== VOLUME =====
    df["volume_mean_10"] = df["volume"].rolling(10).mean()
    df["volume_ratio"] = df["volume"] / df["volume_mean_10"]

    # ===== LAGS =====
    for lag in range(1, 6):
        df[f"close_lag_{lag}"] = df["close"].shift(lag)
        df[f"return_lag_{lag}"] = df["return"].shift(lag)

    # ===== ROLLING STATS =====
    df["rolling_mean_10"] = df["close"].rolling(10).mean()
    df["rolling_std_10"] = df["close"].rolling(10).std()

    # ===== TIME FEATURES =====
    df["hour"] = df["time"].dt.hour
    df["day_of_week"] = df["time"].dt.dayofweek

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

    # ===== TARGET =====
    df["target"] = df["close"].shift(-1)

    return df

def get_last_operations(token):
    a = []

    with get_client(token) as client:
        operations = client.operations.get_operations(account_id=get_account(token).accounts[0].id)
        portfolio = client.operations.get_portfolio(account_id=get_account(token).accounts[0].id)

    for port in portfolio.positions:
        for op in operations.operations:
            if port.position_uid == op.position_uid and port.figi == op.figi:
                if op.type != 'Удержание комиссии за операцию':
                    a.append(op)
                    break
    return a

def get_current_prices(client, figis):
    prices = client.market_data.get_last_prices(figi=figis)

    return {
        p.figi: q_to_float(p.price)
        for p in prices.last_prices
    }


def q_to_float(q):
    return q.units + q.nano / 1e9

def calculate_metrics(position):
    quantity = position.quantity.units + position.quantity.nano / 1e9

    avg_price_q = position.average_position_price
    cur_price_q = position.current_price

    avg_price = avg_price_q.units + avg_price_q.nano / 1e9
    cur_price = cur_price_q.units + cur_price_q.nano / 1e9

    invested = avg_price * quantity
    current_value = cur_price * quantity

    profit = current_value - invested

    yield_pct = (profit / invested * 100) if invested else 0

    return {
        "figi": position.figi,
        "quantity": quantity,
        "buy_price": round(avg_price, 2),
        "current_price": round(cur_price, 2),
        "invested": round(invested, 2),
        "current_value": round(current_value, 2),
        "profit": round(profit, 2),
        "yield_pct": round(yield_pct, 2),
    }

def build_portfolio_distribution_chart(portfolio):
    labels = []
    values = []

    total = sum(
        stock["metrics"]["current_value"]
        for stock in portfolio["stocks"]
    )

    for stock in portfolio["stocks"]:
        value = stock["metrics"]["current_value"]

        if value <= 0:
            continue

        labels.append(stock["name"])
        values.append(round(value / total * 100, 2))

    return {
        "labels": labels,
        "values": values
    }

from cryptography.fernet import Fernet
from django.conf import settings
def decrypt(value: str) -> str:
    cipher = Fernet(settings.SECRET_ENCRYPTION_KEY)
    return cipher.decrypt(value.encode()).decode()
def encrypt(value: str) -> str:
    cipher = Fernet(settings.SECRET_ENCRYPTION_KEY)
    return cipher.encrypt(value.encode()).decode()