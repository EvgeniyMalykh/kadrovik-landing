from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('employees', '0003_employee_salary_nullable')]
    operations = [
        migrations.AddField(model_name='employee', name='marital_status',
            field=models.CharField(blank=True, choices=[('','—'),('single','Холост / Не замужем'),('married','Женат / Замужем'),('divorced','Разведён / Разведена'),('widowed','Вдовец / Вдова')], default='', max_length=30, verbose_name='Семейное положение')),
        migrations.AddField(model_name='employee', name='citizenship',
            field=models.CharField(blank=True, default='Российская Федерация', max_length=100, verbose_name='Гражданство')),
    ]
