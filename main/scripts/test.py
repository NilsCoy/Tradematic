from datetime import datetime, timedelta

import pandas as pd
from main.scripts.api import (
    get_client,
    get_daily_data,
    get_hourly_data,
    get_monthly_data,
    get_weekly_data,
    save_to_csv,
)
from main.scripts.model import predict_data_from_array, preload_model


def start() -> None:
    # create_model()

    # model = preload_model('lstm_model_v1.keras')

    TOKEN = 't.Z5u4o9fbLlLe4vVkyb8Q_c61tpCT3dr2kNl5YJvA73CvWPibBhu2AFWPe7OKSceYDySLQ_8lcs7rOTQW0mKdNQ'  # TODO: Вынести в настройки с подтягиванием из локальных переменных. Небезопасное хранение
    FIGI = 'TCS00A106YF0'
    data = []
    with get_client(TOKEN) as client:
        data = get_hourly_data(
            client, FIGI, hours=24 * 365 * 10
        )  # TODO: Переменная перезаписывается. Стоит либо объявлять разные, либо применять цепочку обработки
        save_to_csv(data, filename='datasets/hourly_data.csv')
        data = get_daily_data(client, FIGI, days=365 * 10)
        save_to_csv(data, filename='datasets/daily_data.csv')
        data = get_weekly_data(client, FIGI, weeks=52 * 10)
        save_to_csv(data, filename='datasets/weekly_data.csv')
        data = get_monthly_data(client, FIGI, months=12 * 10)
        save_to_csv(data, filename='datasets/monthly_data.csv')
    # plot_stock_price(data)


def test() -> None:
    df = pd.read_csv('datasets/stock_data.csv', encoding='CP1251')
    data = df['Цена'].tolist()

    model = preload_model('lstm_model_hourly.keras')
    predicted_data = predict_data_from_array(data, model, 30)
    print(data[-1], predicted_data)


if __name__ == '__main__':
    print(datetime.now() + timedelta(hours=1))
    pass
