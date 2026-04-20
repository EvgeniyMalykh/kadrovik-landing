import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0001_initial'),
        ('events', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notify_birthdays', models.BooleanField(default=True, verbose_name='Дни рождения')),
                ('notify_vacations', models.BooleanField(default=True, verbose_name='Начало/конец отпусков')),
                ('notify_probation', models.BooleanField(default=True, verbose_name='Испытательный срок')),
                ('notify_contracts', models.BooleanField(default=True, verbose_name='Истечение договоров')),
                ('notify_subscription', models.BooleanField(default=True, verbose_name='Подписка (истечение)')),
                ('company', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='notification_settings', to='companies.company', verbose_name='Компания')),
            ],
            options={
                'verbose_name': 'Настройки уведомлений',
                'verbose_name_plural': 'Настройки уведомлений',
            },
        ),
    ]
