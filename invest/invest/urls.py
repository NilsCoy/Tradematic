"""
URL configuration for invest project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from main.views import index_page, blog_page, about_page, panel, check_auth

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index_page, name='index_page'),
    path('blog/', blog_page, name='blog_page'),
    path('about/', about_page, name='about_page'),
    path('panel/', panel, name='panel'),
    path('api/check_auth/', check_auth, name='check_auth'),
    #path('logout/', user_logout, name='user_logout'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_URL)

