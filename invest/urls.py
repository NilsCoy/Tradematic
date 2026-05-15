from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from main.scripts.auth import check_auth
from main.views import about_page, blog_page, chat_api, get_chart, index_page, panel, ragpipe_chat


urlpatterns = [
    path('admin/', admin.site.urls),
    path('blog/', blog_page, name='blog_page'),
    path('about/', about_page, name='about_page'),
    path('panel/', panel, name='panel'),
    path('chat/', chat_api, name='chat_api'),
    path('api/check_auth/', check_auth, name='check_auth'),
    path('api/ragpipe/chat/', ragpipe_chat, name='ragpipe_chat'),
    path('', index_page, name='index_page'),
    path('get_chart/', get_chart, name='get_chart'),
    # path('logout/', logout_user, name='logout_user'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
