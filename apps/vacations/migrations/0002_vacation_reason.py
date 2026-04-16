from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vacations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='vacation',
            name='reason',
            field=models.TextField(blank=True, default='', verbose_name='Причина / основание'),
        ),
    ]
