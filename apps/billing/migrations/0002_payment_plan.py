from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
    ]
    operations = [
        migrations.AddField(
            model_name="payment",
            name="plan",
            field=models.CharField(default="start", max_length=20, verbose_name="Тариф"),
        ),
    ]
