from django.contrib import messages
from main.models import UserTokens
from main.scripts.model import *
from main.scripts.api import *
from django.shortcuts import redirect

import pandas as pd
import json

def add_portfolio(r, c):
    username = r.user
    token = r.POST['Token']
    if not token:
        messages.error(r, 'Неверный токен!')
    else:
        obj, created = UserTokens.objects.get_or_create(
            username=username,
            token=token,
            defaults={'username': username, 'token': token}
        )
        if not created:
            messages.error(r, 'Токен уже добавлен!')
    return redirect('panel')

def remove_portfolio(r, c):
    username = str(r.user)
    token_id = r.POST
    portfolio = get_portfolio(username)
    for j in portfolio:
        if str(j['id']) in str(token_id):
            UserTokens.objects.filter(username=username, token=j['token']).delete()
    return redirect('panel')

def get_portfolio(username):
    tokens = list(UserTokens.objects.filter(username=username).values_list('token', flat=True))
    content = []

    for token in tokens:
        account = get_account(token)

        portfolio = {}

        portfolio['token'] = token
        portfolio['name'] = account.accounts[0].name
        portfolio['type'] = account.accounts[0].type
        portfolio['id'] = account.accounts[0].id
        portfolio['status'] = account.accounts[0].name

        portfolio['stocks'] = get_elements_in_portfolio(token)

        total_cost = 0
        total_stocks = 0
        for i in portfolio['stocks']:
            total_cost += i['cur_price'] * i['quantity']
            if i['instrument_type'] != 'currency':
                total_stocks += i['quantity']
        portfolio['total_cost'] = round(total_cost,2)
        portfolio['total_stocks'] = int(total_stocks)

        content.append(portfolio)

    return content

def chart_view(token, figi):
    with get_client(token) as client:
        data = get_hourly_data(client, figi, hours=24 * 3)
        save_to_csv(data,'main/scripts/datasets/stock_data.csv')

    df = pd.read_csv('main/scripts/datasets/stock_data.csv', encoding='CP1251')
    data = df['Цена'].tolist()
    labels = df['Дата'].tolist()
    labels = [x.split('+')[0] for x in labels]
    labels.append(str(datetime.now() + timedelta(hours=1)).split('.')[0])
    labels.append(str(datetime.now() + timedelta(hours=2)).split('.')[0])
    labels.append(str(datetime.now() + timedelta(hours=3)).split('.')[0])

    model = preload_model('lstm_model_hourly.keras')
    predicted_data = data.copy()
    predicted_data.append(float(predict_data_from_array(data, model, 30)))
    predicted_data.append(float(predict_data_from_array(predicted_data, model, 30)))
    predicted_data.append(float(predict_data_from_array(predicted_data, model, 30)))

    chart = {
        'labels': json.dumps(labels),
        'data': json.dumps(data),
        'predict_data': predicted_data,
        'title': get_name_stock(token, figi),
        'chart_type': 'line'  # Может быть 'bar', 'pie', 'doughnut' и т.д.
    }

    return chart

def get_charts(username, profile_id):
    portfolio = get_portfolio(username)
    charts = []
    for i in portfolio:
        if str(i['id']) in str(profile_id):
            for stock in i['stocks']:
                if stock['instrument_type'] != 'currency':
                    charts.append(chart_view(i['token'], stock['figi']))
    return charts