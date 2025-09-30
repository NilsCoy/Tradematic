from django.contrib import admin
from .models import UserTokens

# Регистрация модели
@admin.register(UserTokens)
class UserTokenAdmin(admin.ModelAdmin):
    #list_display = ('username', 'token', 'created_at')  # Поля, отображаемые в списке
    list_display = ('username', 'short_token', 'created_at')
    search_fields = ('username', 'token')  # Поля для поиска
    list_filter = ('created_at',)  # Фильтры справа
    readonly_fields = ('created_at',)  # Запрет редактирования поля
    actions = ['delete_selected']

    def short_token(self, obj):
        return obj.token[:10] + '...' if len(obj.token) > 10 else obj.token
    short_token.short_description = 'Токен'