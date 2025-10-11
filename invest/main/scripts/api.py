import csv
from contextlib import contextmanager
from datetime import datetime, timedelta

import grpc
import matplotlib.pyplot as plt
import tinkoff.invest as ti
from tinkoff.invest import InstrumentIdType
from tqdm import tqdm


# Инициализация клиента
@contextmanager
def get_client(token):
    """Получает клинета по токену"""
    client = ti.Client(token)
    try:
        yield client
    except grpc.RpcError as e:
        print(f'Ошибка получения данных: {e.details()}')


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
        portfolio = client.operations.get_portfolio(account_id=get_account(token).accounts[0].id)
        a = []
        for position in portfolio.positions:
            item = {}

            pos_type = position.instrument_type
            figi = position.figi
            quantity = position.quantity.units + position.quantity.nano / 1e9
            average_price = position.average_position_price
            current_price = position.current_price

            if average_price:
                avg_price = average_price.units + average_price.nano / 1e9
            if current_price:
                cur_price = current_price.units + current_price.nano / 1e9

            item['figi'] = figi
            item['quantity'] = quantity
            item['avg_price'] = avg_price
            item['cur_price'] = cur_price
            item['instrument_type'] = pos_type

            a.append(item)

        return a


def get_name_stock(token, figi):
    """Получает название инструмента по FIGI"""
    with get_client(token) as client:
        instrument = client.instruments.get_instrument_by(id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi)
        if instrument.instrument:
            return instrument.instrument.name
    return None
