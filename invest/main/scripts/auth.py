from django.contrib.auth import authenticate, login, logout, models, update_session_auth_hash
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.template.context_processors import request
from django.contrib.auth.hashers import check_password
from django.contrib import messages

def check_auth(r):
    return JsonResponse({
        'authenticated': r.user.is_authenticated,
        'username': r.user.username if r.user.is_authenticated else None
    })

def user_login(r):
    print('login func')
    email = r.POST['Email']
    password = r.POST['Password']
    user = authenticate(r, username=email, password=password)
    if user is not None:
        login(r, user=user)
        return redirect('panel')

def user_register(r):
    print('register func')
    email = r.POST['Email']
    password = r.POST['Password']
    if models.User.objects.filter(email=email).exists():
        return render(r, 'index.html', {'error': 'Пользователь с таким email уже существует!'})

    user_class = models.User.objects.create_user(
        username=email,
        email=email,
        password=password
    )
    user_group, created = models.Group.objects.get_or_create(name='user')
    user_class.groups.add(user_group)
    user_class.save()

    user = authenticate(r, username=email, password=password)
    if user is not None:
        login(r, user)
        return redirect('panel')
    return render(r, 'index.html', {'error': 'Ошибка пользователя!'})

def user_logout(r):
    print('logout func')
    logout(r)
    return redirect('index_page')

def reset_password(r, c):
    print('reset_password func')
    password = r.POST['Password']
    new_password = r.POST['New_Password']
    new_password2 = r.POST['New_Password2']

    if not check_password(password, r.user.password):
        messages.error(r, 'Неверный текущий пароль')
        return render(r, 'panel.html', c)

    if new_password != new_password2:
        messages.error(r, 'Новые пароли не совпадают')
        return render(r, 'panel.html', c)

    r.user.set_password(new_password)
    r.user.save()

    update_session_auth_hash(r, r.user)

    messages.success(r, 'Пароль успешно изменён!')
    return render(r, 'panel.html', c)