from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('employees', '0001_initial')]
    operations = [
        migrations.AddField(
            model_name='employee',
            name='birth_place',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Место рождения'),
        ),
        migrations.AddField(
            model_name='employee',
            name='education',
            field=models.CharField(
                blank=True,
                choices=[('', '—'), ('secondary', 'Среднее'), ('secondary_special', 'Среднее специальное'), ('incomplete_higher', 'Неполное высшее'), ('higher', 'Высшее'), ('two_higher', 'Два высших'), ('postgraduate', 'Аспирантура / учёная степень')],
                default='',
                max_length=50,
                verbose_name='Образование',
            ),
        ),
    ]
