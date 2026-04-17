from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('employees', '0004_employee_marital_citizenship')]
    operations = [
        migrations.CreateModel(
            name='SalaryHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('salary', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Оклад')),
                ('effective_date', models.DateField(verbose_name='Дата вступления в силу')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('employee', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='salary_history',
                    to='employees.employee',
                    verbose_name='Сотрудник',
                )),
            ],
            options={
                'verbose_name': 'История оклада',
                'verbose_name_plural': 'История окладов',
                'ordering': ['-effective_date', '-created_at'],
            },
        ),
    ]
