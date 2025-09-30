import os
from tensorflow.keras.models import load_model
from sklearn.preprocessing import MinMaxScaler
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def preload_model(name=''):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(script_dir, '..', 'models')
    models_dir = os.path.normpath(models_dir)  # Убирает '..'
    model_path = os.path.join(models_dir, name)
    if os.path.exists(model_path):
        #print(f"Загружается модель из {model_path}\n")
        return load_model(model_path)
    else:
        print("Модель не найдена!")
        return None


# Функция для подготовки данных для обучения RNN
def prepare_data(candles, time_steps=10):
    prices = np.array([float(candle.close.units) + candle.close.nano / 1e9 for candle in candles])
    scaler = MinMaxScaler(feature_range=(0, 1))
    prices_scaled = scaler.fit_transform(prices.reshape(-1, 1))

    X, y = [], []
    for i in range(len(prices_scaled) - time_steps):
        X.append(prices_scaled[i:i + time_steps])
        y.append(prices_scaled[i + time_steps])

    return np.array(X), np.array(y), scaler

def predict_data_from_candle(data, model, len_input=24):
    prices = np.array([float(candle.close.units) + candle.close.nano / 1e9 for candle in data[-(len_input+1):-1]])
    scaler = MinMaxScaler(feature_range=(0, 1))
    prices_scaled = scaler.fit_transform(prices.reshape(-1, 1))
    future_pred = model.predict(prices_scaled.reshape(1, len_input, 1))
    future_price = scaler.inverse_transform(future_pred.reshape(-1, 1))
    return future_price[0][0]

def predict_data_from_array(data, model, len_input=24):
    prices = np.array([candle for candle in data[-len_input:]])
    scaler = MinMaxScaler(feature_range=(0, 1))
    prices_scaled = scaler.fit_transform(prices.reshape(-1, 1))
    future_pred = model.predict(prices_scaled.reshape(1, len_input, 1))
    future_price = scaler.inverse_transform(future_pred.reshape(-1, 1))
    return future_price[0][0]