from django.contrib.auth import authenticate, login, logout, models, update_session_auth_hash
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.hashers import check_password
from django.contrib import messages


def check_auth(request):
    return JsonResponse(
        {
            'authenticated': request.user.is_authenticated,
            'username': request.user.username if request.user.is_authenticated else None,
        }
    )


def login_user(request):
    print('login func')
    email = request.POST['Email']
    password = request.POST['Password']
    user = authenticate(request, username=email, password=password)
    if user is not None:
        login(request, user=user)
        return redirect('panel')


def register_user(request):
    print('register func')
    email = request.POST['Email']
    password = request.POST['Password']
    if models.User.objects.filter(email=email).exists():
        return render(request, 'index.html', {'error': 'Пользователь с таким email уже существует!'})

    user_class = models.User.objects.create_user(username=email, email=email, password=password)
    user_group, _ = models.Group.objects.get_or_create(name='user')
    user_class.groups.add(user_group)
    user_class.save()

    user = authenticate(request, username=email, password=password)
    if user is not None:
        login(request, user)
        return redirect('panel')
    return render(request, 'index.html', {'error': 'Ошибка пользователя!'})


def logout_user(request):
    print('logout func')
    logout(request)
    return redirect('index_page')


def reset_password(request, context):
    print('reset_password func')
    password = request.POST['Password']
    new_password = request.POST['New_Password']
    new_password2 = request.POST['New_Password2']

    if not check_password(password, request.user.password):
        messages.error(request, 'Неверный текущий пароль')
        return render(request, 'panel.html', context)

    if new_password != new_password2:
        messages.error(request, 'Новые пароли не совпадают')
        return render(request, 'panel.html', context)

    request.user.set_password(new_password)
    request.user.save()

    update_session_auth_hash(request, request.user)

    messages.success(request, 'Пароль успешно изменён!')
    return render(request, 'panel.html', context)
