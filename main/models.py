from django.db import models

# Create your models here.


class UserTokens(models.Model):
    username = models.CharField(max_length=255, verbose_name='Имя пользователя')
    token = models.CharField(max_length=255, verbose_name='Токен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    def __str__(self) -> str:
        return f'{self.username} {self.token}'

    class Meta:
        db_table = 'tokens'
        ordering = ('username', '-created_at')
        verbose_name = 'Токен пользователя'
        verbose_name_plural = 'Токены пользователей'
        unique_together = (('username', 'token'),)
        indexes = [  # noqa: RUF012
            models.Index(fields=['username']),  # Индекс для сортировки по имени
            models.Index(fields=['-created_at']),  # Индекс для обратной сортировки по дате
        ]
