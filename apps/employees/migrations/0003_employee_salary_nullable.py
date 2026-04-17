from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('employees', '0002_employee_birth_place_education')]
    operations = [
        migrations.AlterField(
            model_name='employee',
            name='salary',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=12, null=True, verbose_name='Оклад'),
        ),
    ]
