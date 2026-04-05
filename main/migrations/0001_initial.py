from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='UserTokens',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(max_length=255, verbose_name='Имя пользователя')),
                ('token', models.CharField(max_length=255, verbose_name='Токен')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')),
            ],
            options={
                'verbose_name': 'Токен пользователя',
                'verbose_name_plural': 'Токены пользователей',
                'db_table': 'tokens',
                'ordering': ['username', '-created_at'],
                'indexes': [
                    models.Index(fields=['username'], name='tokens_usernam_6765ff_idx'),
                    models.Index(fields=['-created_at'], name='tokens_created_8df85f_idx'),
                ],
            },
        ),
    ]
