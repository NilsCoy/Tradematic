import os

import numpy as np
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import load_model


def preload_model(name=''):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(script_dir, '..', 'models')
    models_dir = os.path.normpath(models_dir)  # Убирает '..'
    model_path = os.path.join(models_dir, name)
    if os.path.exists(model_path):
        # print(f"Загружается модель из {model_path}\n")
        return load_model(model_path)
    else:
        print('Модель не найдена!')
        return None


# Функция для подготовки данных для обучения RNN
def prepare_data(candles, time_steps=10):
    prices = np.array([float(candle.close.units) + candle.close.nano / 1e9 for candle in candles])
    scaler = MinMaxScaler(feature_range=(0, 1))
    prices_scaled = scaler.fit_transform(prices.reshape(-1, 1))

    X, y = [], []
    for i in range(len(prices_scaled) - time_steps):
        X.append(prices_scaled[i : i + time_steps])
        y.append(prices_scaled[i + time_steps])

    return np.array(X), np.array(y), scaler

def prepare_data_from_array(prices, time_steps=10):
    scaler = MinMaxScaler(feature_range=(0, 1))
    prices_scaled = scaler.fit_transform(np.array(prices).reshape(-1, 1))

    X, y = [], []
    for i in range(len(prices_scaled) - time_steps):
        X.append(prices_scaled[i : i + time_steps])
        y.append(prices_scaled[i + time_steps])

    return np.array(X), np.array(y), scaler


def predict_data_from_candle(data, model, len_input=24):
    prices = np.array([float(candle.close.units) + candle.close.nano / 1e9 for candle in data[-(len_input + 1) : -1]])
    scaler = MinMaxScaler(feature_range=(0, 1))
    prices_scaled = scaler.fit_transform(prices.reshape(-1, 1))
    future_pred = model.predict(prices_scaled.reshape(1, len_input, 1), verbose=0)
    future_price = scaler.inverse_transform(future_pred.reshape(-1, 1))
    return future_price[0][0]


def predict_data_from_array(data, model, len_input=24):
    prices = np.array([candle for candle in data[-len_input:]])
    scaler = MinMaxScaler(feature_range=(0, 1))
    prices_scaled = scaler.fit_transform(prices.reshape(-1, 1))
    future_pred = model.predict(prices_scaled.reshape(1, len_input, 1), verbose=0)
    future_price = scaler.inverse_transform(future_pred.reshape(-1, 1))
    return future_price[0][0]


def get_offset(data, model, len_input=24*30*6):
    prices = np.array([candle for candle in data[-len_input:]])

    X, y, scaler = prepare_data_from_array(prices)

    predictions = model.predict(X, verbose=0)
    predictions = scaler.inverse_transform(predictions)  # Обратное масштабирование
    y = scaler.inverse_transform(y)

    offset = np.mean(y) - np.mean(predictions)
    return offset

def get_slice_data(data, window=24, slice=30):
    data = data[-slice*window:]
    new_data = [float(np.mean(data[i:i+window])) for i in range(len(data)-window)]
    return new_data

def get_unique_slice_data(data, window=24, slice=30):
    data = data[-slice*window:]
    new_data = [float(np.mean(data[i*window:i*window+window])) for i in range(len(data)//window)]
    return new_data
