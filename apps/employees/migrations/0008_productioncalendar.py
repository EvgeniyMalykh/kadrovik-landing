from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('employees', '0007_rename_od_to_do')]
    operations = [
        migrations.CreateModel(
            name='ProductionCalendar',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True, verbose_name='Дата')),
                ('day_type', models.CharField(
                    choices=[('holiday', 'Праздничный/выходной'), ('short', 'Предпраздничный сокращённый')],
                    max_length=20, verbose_name='Тип дня',
                )),
                ('description', models.CharField(blank=True, max_length=200, verbose_name='Описание')),
            ],
            options={
                'verbose_name': 'Производственный календарь',
                'verbose_name_plural': 'Производственный календарь',
                'ordering': ['date'],
            },
        ),
    ]
