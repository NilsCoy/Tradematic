from django.http.response import HttpResponse
from django.shortcuts import render
from main.scripts.auth import login_user, logout_user, register_user, reset_password
from main.scripts.porfolio import add_portfolio, get_charts, get_portfolio, remove_portfolio, chart_view, get_portfolio_from_id, get_portfolio_summary
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


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
    except Exception:
        pass
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

@csrf_exempt
def get_chart(request):
    token = get_portfolio_from_id(request.user, request.GET.get('id'))['token']
    figi = request.GET.get('figi')

    if not token or not figi:
        return JsonResponse({'error': 'Missing parameters'}, status=400)

    try:
        chart = chart_view(token, figi)
        return JsonResponse(chart)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)