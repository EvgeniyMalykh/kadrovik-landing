from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('vacations', '0005_add_north_and_extra_leave'),
    ]

    operations = [
        migrations.AddField(
            model_name='vacationschedule',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name='Последнее обновление'),
        ),
    ]
