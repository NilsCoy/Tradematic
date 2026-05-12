import json
from datetime import datetime, timedelta

import pandas as pd
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from main.scripts.api import (
    get_account,
    get_client,
    get_elements_in_portfolio,
    get_daily_data,
    get_name_stock,
    save_to_csv,
    calculate_metrics,
    decrypt,
    encrypt,
    build_portfolio_distribution_chart
)
from main.scripts.model import predict_data_from_array, preload_model, get_offset, get_slice_data, get_unique_slice_data

from main.models import UserTokens

def add_portfolio(request):
    username = request.user
    token = request.POST['Token']

    if not token:
        messages.error(request, 'Неверный токен!')
        return redirect('panel')

    _, created = UserTokens.objects.get_or_create(
        username=username,
        token=encrypt(token),
    )

    if not created:
        messages.error(request, 'Токен уже добавлен!')

    return redirect('panel')


def remove_portfolio(request):
    username = str(request.user)
    token_id = request.POST
    portfolio = get_portfolio(username)
    for j in portfolio:
        if str(j['id']) in str(token_id):
            UserTokens.objects.filter(username=username, token=j['token']).delete()
    return redirect('panel')


def get_portfolio(username):
    tokens = list(UserTokens.objects.filter(username=username).values_list('token', flat=True))
    content = []

    for token in tokens:
        token = decrypt(token)
        account = get_account(token)

        portfolio = {}

        portfolio['token'] = token
        portfolio['name'] = account.accounts[0].name
        portfolio['type'] = account.accounts[0].type
        portfolio['id'] = account.accounts[0].id
        portfolio['status'] = account.accounts[0].name

        portfolio['stocks'] = get_elements_in_portfolio(token)
        # print(portfolio['stocks'])
        # portfolio['metrics'] = calculate_metrics(token)

        total_cost = 0
        total_stocks = 0
        for i in portfolio['stocks']:
            total_cost += i['cur_price'] * i['quantity']
            if i['instrument_type'] != 'currency':
                total_stocks += i['quantity']
        portfolio['total_cost'] = round(total_cost, 2)
        portfolio['total_stocks'] = int(total_stocks)

        content.append(portfolio)

    return content


def chart_view(token, figi):
    with get_client(token) as client:
        data = get_daily_data(client, figi, days=365*4)
        save_to_csv(data, 'main/scripts/datasets/stock_data.csv')

    df = pd.read_csv('main/scripts/datasets/stock_data.csv', encoding='CP1251')
    df = df.sort_values('Дата')
    data = df['Цена'].tolist()
    labels = df['Дата'].tolist()
    labels = [x.split('+')[0].split(' ')[0] for x in labels[-60:]]

    model = preload_model('lstm_model_hourly_v2.keras')

    predicted_data = [None for i in range(len(data[-59:]))] #data[-60:].copy()
    predicted_data.append(data[-60:][-1])

    predicted_data.append(float(predict_data_from_array(data, model, 30) + get_offset(data[-30:], model)))
    labels.append(str(datetime.fromisoformat(labels[-1]) + timedelta(days=1)).split('.')[0].split(' ')[0])

    for i in range(1, 29):
        days_data = get_slice_data(data, i+1, 30)
        predicted_data.append(float(predict_data_from_array(days_data, model, 30) + get_offset(days_data[-30:], model)))
        labels.append(str(datetime.fromisoformat(labels[-1]) + timedelta(days=1)).split('.')[0].split(' ')[0])

    chart = {
        'labels': json.dumps(labels),
        'data': json.dumps(data[-60:]),
        'predict_data': predicted_data,
        'title': get_name_stock(token, figi),
        'chart_type': 'line',  # Может быть 'bar', 'pie', 'doughnut' и т.д.
    }

    return chart

def get_portfolio_from_id(username, token_id):
    for portfolio in get_portfolio(username):
        if str(portfolio['id']) in str(token_id):
            return portfolio

def get_charts(username, profile_id):
    portfolio = get_portfolio_from_id(username, profile_id)
    charts = []
    for stock in portfolio['stocks']:
        print(stock['instrument_type'])
        if stock['instrument_type'] != 'currency':
            charts.append(chart_view(portfolio['token'], stock['figi']))
    return charts



def get_portfolio_summary(portfolio):
    metrics = [
        item["metrics"]
        for item in portfolio["stocks"]
        if item.get("metrics")
    ]

    if not metrics:
        return None

    total_invested = sum(m["invested"] for m in metrics)
    total_value = sum(m["current_value"] for m in metrics)
    total_profit = sum(m["profit"] for m in metrics)

    total_yield = (
        total_profit / total_invested * 100
        if total_invested else 0
    )

    avg_yield = (
        sum(m["yield_pct"] for m in metrics) / len(metrics)
    )

    best = max(metrics, key=lambda x: x["yield_pct"])
    worst = min(metrics, key=lambda x: x["yield_pct"])

    best_name = next(
        (
            stock["name"]
            for stock in portfolio["stocks"]
            if stock["figi"] == best["figi"]
        ),
        None
    )

    worst_name = next(
        (
            stock["name"]
            for stock in portfolio["stocks"]
            if stock["figi"] == worst["figi"]
        ),
        None
    )

    return {
        "total_invested": round(total_invested, 2),
        "total_value": round(total_value, 2),
        "total_profit": round(total_profit, 2),
        "total_yield_pct": round(total_yield, 2),
        "avg_yield_pct": round(avg_yield, 2),

        "best": {
            "name": best_name,
            "yield_pct": best["yield_pct"],
            "profit": best["profit"]
        },

        "worst": {
            "name": worst_name,
            "yield_pct": worst["yield_pct"],
            "profit": worst["profit"]
        },

        "distribution": build_portfolio_distribution_chart(portfolio)
    }