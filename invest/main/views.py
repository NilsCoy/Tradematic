from django.shortcuts import render, redirect
from main.scripts.auth import *
from main.scripts.porfolio import *

def index_page(r):
    if r.POST:
        if 'form-login' in r.POST:
            return user_login(r)
        elif 'form-register' in r.POST:
            return user_register(r)
        elif 'form-reset' in r.POST:
            pass

    return render(r, 'index.html')
def blog_page(r):
    return render(r, 'blog.html')
def about_page(r):
    return render(r, 'about.html')


def panel(r):
    page = r.GET.get('page', 'default')
    templates = {
        'default': 'panel_profile.html',
        'profile': 'panel_profile.html',
        'portfolio': 'panel_portfolio.html',
        'token': 'panel_portfolio_token.html'
    }
    var = {
        'username': r.user,
        'tokens': get_portfolio(r.user),
        'self_token': None,
        'charts': []
    }

    try:
        var['self_token'] = page.split('-')[1]
        var['charts'] = get_charts(r.user, var['self_token'])
    except:
        var['self_token'] = None
        var['charts'] = []
    context = {
        'page': page,
        'template': templates.get(page.split('-')[0], 'panel_profile.html'),
        'var': var,
    }

    if r.POST:
        if 'form-logout' in r.POST:
            return user_logout(r)
        elif 'reset-password' in r.POST:
            return reset_password(r, context)
        elif 'add-token' in r.POST:
            return add_portfolio(r, context)
        elif 'remove-token' in r.POST:
            return remove_portfolio(r, context)

    if not r.user.is_authenticated:
        return user_logout(r)

    #return chart_view(r, context)

    return render(r, 'panel.html', context)
