
from main.scripts.model import *
from main.scripts.api import *

def start():
    # create_model()

    #model = preload_model('lstm_model_v1.keras')

    TOKEN = "t.Z5u4o9fbLlLe4vVkyb8Q_c61tpCT3dr2kNl5YJvA73CvWPibBhu2AFWPe7OKSceYDySLQ_8lcs7rOTQW0mKdNQ"
    FIGI = "TCS00A106YF0"
    data = []
    with get_client(TOKEN) as client:
        data = get_hourly_data(client, FIGI, hours=24*365*10)
        save_to_csv(data, filename='datasets/hourly_data.csv')
        data = get_daily_data(client, FIGI, days=365*10)
        save_to_csv(data, filename='datasets/daily_data.csv')
        data = get_weekly_data(client, FIGI, weeks=52*10)
        save_to_csv(data, filename='datasets/weekly_data.csv')
        data = get_monthly_data(client, FIGI, months=12*10)
        save_to_csv(data, filename='datasets/monthly_data.csv')
    #plot_stock_price(data)

def test():
    df = pd.read_csv('datasets/stock_data.csv', encoding='CP1251')
    data = df['Цена'].tolist()

    model = preload_model('lstm_model_hourly.keras')
    predicted_data = predict_data_from_array(data, model, 30)
    print(data[-1], predicted_data)

if __name__ == '__main__':
    print(datetime.now() + timedelta(hours=1))
    pass


