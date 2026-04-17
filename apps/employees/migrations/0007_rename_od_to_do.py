from django.db import migrations, models


def rename_od_to_do(apps, schema_editor):
    TimeRecord = apps.get_model('employees', 'TimeRecord')
    TimeRecord.objects.filter(code='ОД').update(code='ДО')


def rename_do_to_od(apps, schema_editor):
    TimeRecord = apps.get_model('employees', 'TimeRecord')
    TimeRecord.objects.filter(code='ДО').update(code='ОД')


class Migration(migrations.Migration):
    dependencies = [('employees', '0006_timerecord_add_rv_overtime_codes')]
    operations = [
        migrations.RunPython(rename_od_to_do, rename_do_to_od),
        migrations.AlterField(
            model_name='timerecord',
            name='code',
            field=models.CharField(
                'Код',
                max_length=3,
                choices=[
                    ('Я',  'Явка (рабочий день)'),
                    ('ОТ', 'Отпуск ежегодный'),
                    ('ДО', 'Отпуск доп.'),
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
