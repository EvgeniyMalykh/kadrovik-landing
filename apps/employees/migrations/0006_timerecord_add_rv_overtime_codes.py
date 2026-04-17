from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('employees', '0005_salaryhistory')]
    operations = [
        migrations.AlterField(
            model_name='timerecord',
            name='code',
            field=models.CharField(
                'Код',
                max_length=3,
                choices=[
                    ('Я',  'Явка (рабочий день)'),
                    ('ОТ', 'Отпуск ежегодный'),
                    ('ОД', 'Отпуск доп.'),
                    ('Б',  'Больничный'),
                    ('П',  'Праздник'),
                    ('В',  'Выходной'),
                    ('К',  'Командировка'),
                    ('НН', 'Неявка невыясненная'),
                    ('Я½', 'Неполный день'),
                    ('РВ', 'Работа в выходной'),
                    ('Я/С', 'Сверхурочные'),
                ],
                default='Я',
            ),
        ),
    ]
