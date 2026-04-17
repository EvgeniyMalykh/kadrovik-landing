from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_payment_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='payment_method_id',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='ИД метода оплаты (рекуррент)'),
        ),
        migrations.AddField(
            model_name='subscription',
            name='auto_renew',
            field=models.BooleanField(default=False, verbose_name='Автопродление'),
        ),
    ]
