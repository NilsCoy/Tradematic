import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.http.response import HttpResponse
from django.shortcuts import render
from main.scripts.auth import login_user, logout_user, register_user, reset_password
from main.scripts.porfolio import (
    add_portfolio,
    chart_view,
    get_portfolio,
    get_portfolio_from_id,
    get_portfolio_summary,
    remove_portfolio,
)
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


def index_page(request):
    if request.POST:
        if 'form-login' in request.POST:
            return login_user(request)
        elif 'form-register' in request.POST:
            return register_user(request)
        elif 'form-reset' in request.POST:
            pass

    return render(request, 'index.html')


def blog_page(request) -> HttpResponse:
    return render(request, 'blog.html')


def about_page(request) -> HttpResponse:
    return render(request, 'about.html')


def panel(request):
    page = request.GET.get('page', 'default')
    templates = {
        'default': 'panel_profile.html',
        'profile': 'panel_profile.html',
        'portfolio': 'panel_portfolio.html',
        'token': 'panel_portfolio_token.html',
    }
    var = {'username': request.user, 'tokens': get_portfolio(request.user), 'self_token': '', 'portfolio': None}

    try:
        var['self_token'] = page.split('-')[1]
        # var['charts'] = get_charts(request.user, var['self_token'])
        var['portfolio'] = get_portfolio_from_id(request.user, var['self_token'])
        var['metrics'] = get_portfolio_summary(var['portfolio'])
    except (IndexError, KeyError, TypeError):
        var['self_token'] = ''
    context = {
        'page': page,
        'template': templates.get(page.split('-')[0], 'panel_profile.html'),
        'var': var,
    }

    if request.POST:
        if 'form-logout' in request.POST:
            return logout_user(request)
        elif 'reset-password' in request.POST:
            return reset_password(request, context)
        elif 'add-token' in request.POST:
            return add_portfolio(request)
        elif 'remove-token' in request.POST:
            return remove_portfolio(request)

    if not request.user.is_authenticated:
        return logout_user(request)

    return render(request, 'panel.html', context)


@login_required
def chat_api(request):
    if request.method == 'GET':
        return render(request, 'chat.html')
    if request.method == 'POST':
        return _ragpipe_chat_response(request)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
@require_POST
def get_chart(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    portfolio = get_portfolio_from_id(request.user, payload.get('id'))
    token = portfolio['token'] if portfolio else None
    figi = payload.get('figi')

    if not token or not figi:
        return JsonResponse({'error': 'Missing parameters'}, status=400)

    try:
        chart = chart_view(token, figi)
        return JsonResponse(chart)
    except Exception as e:
        logger.exception('Chart loading failed')
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def ragpipe_chat(request):
    return _ragpipe_chat_response(request)


def _ragpipe_chat_response(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    question = str(payload.get('message', '')).strip()
    if not question:
        return JsonResponse({'error': 'Введите сообщение'}, status=400)

    upstream_payload = json.dumps(
        {
            'question': question,
            'model': 'tradematic-analyst',
            'top_k': 6,
        }
    ).encode('utf-8')
    request_obj = Request(
        f'{settings.EDMI_API_URL}/ragpipe/chat',
        data=upstream_payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urlopen(request_obj, timeout=240) as response:
            data = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        return JsonResponse({'error': f'EDMI API error: {exc.code}'}, status=502)
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return JsonResponse({'error': f'EDMI API unavailable: {exc}'}, status=502)

    return JsonResponse(
        {
            'response': data.get('answer') or '',
            'matches': data.get('matches', []),
            'queries': data.get('queries', []),
        }
    )
