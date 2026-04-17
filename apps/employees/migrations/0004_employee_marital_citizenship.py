from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('employees', '0003_employee_salary_nullable')]
    operations = [
        migrations.AddField(
            model_name='employee',
            name='marital_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('single', 'Не женат / Не замужем'),
                    ('married', 'Женат / Замужем'),
                    ('divorced', 'Разведён / Разведена'),
                    ('widowed', 'Вдовец / Вдова'),
                    ('cohabiting', 'Гражданский брак'),
                ],
                max_length=20,
                null=True,
                verbose_name='Семейное положение',
            ),
        ),
        migrations.AddField(
            model_name='employee',
            name='citizenship',
            field=models.CharField(
                blank=True,
                default='Российская Федерация',
                max_length=100,
                null=True,
                verbose_name='Гражданство',
            ),
        ),
    ]
