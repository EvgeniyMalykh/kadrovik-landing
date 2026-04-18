import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("employees", "0005_salaryhistory")]
    operations = [
        migrations.CreateModel(
            name="TimeRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(verbose_name="\u0414\u0430\u0442\u0430")),
                ("code", models.CharField(
                    "\u041a\u043e\u0434",
                    max_length=3,
                    choices=[
                        ("\u042f",  "\u042f\u0432\u043a\u0430 (\u0440\u0430\u0431\u043e\u0447\u0438\u0439 \u0434\u0435\u043d\u044c)"),
                        ("\u041e\u0422", "\u041e\u0442\u043f\u0443\u0441\u043a \u0435\u0436\u0435\u0433\u043e\u0434\u043d\u044b\u0439"),
                        ("\u041e\u0414", "\u041e\u0442\u043f\u0443\u0441\u043a \u0434\u043e\u043f."),
                        ("\u0411",  "\u0411\u043e\u043b\u044c\u043d\u0438\u0447\u043d\u044b\u0439"),
                        ("\u041f",  "\u041f\u0440\u0430\u0437\u0434\u043d\u0438\u043a"),
                        ("\u0412",  "\u0412\u044b\u0445\u043e\u0434\u043d\u043e\u0439"),
                        ("\u041a",  "\u041a\u043e\u043c\u0430\u043d\u0434\u0438\u0440\u043e\u0432\u043a\u0430"),
                        ("\u041d\u041d", "\u041d\u0435\u044f\u0432\u043a\u0430 \u043d\u0435\u0432\u044b\u044f\u0441\u043d\u0435\u043d\u043d\u0430\u044f"),
                        ("\u042f\u00bd", "\u041d\u0435\u043f\u043e\u043b\u043d\u044b\u0439 \u0434\u0435\u043d\u044c"),
                        ("\u0420\u0412", "\u0420\u0430\u0431\u043e\u0442\u0430 \u0432 \u0432\u044b\u0445\u043e\u0434\u043d\u043e\u0439"),
                        ("\u042f/\u0421", "\u0421\u0432\u0435\u0440\u0445\u0443\u0440\u043e\u0447\u043d\u044b\u0435"),
                    ],
                    default="\u042f",
                )),
                ("hours", models.PositiveSmallIntegerField(default=8, verbose_name="\u0427\u0430\u0441\u043e\u0432")),
                ("employee", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="time_records",
                    to="employees.employee",
                    verbose_name="\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a",
                )),
            ],
            options={
                "verbose_name": "\u041e\u0442\u043c\u0435\u0442\u043a\u0430 \u0442\u0430\u0431\u0435\u043b\u044f",
                "verbose_name_plural": "\u041e\u0442\u043c\u0435\u0442\u043a\u0438 \u0442\u0430\u0431\u0435\u043b\u044f",
                "unique_together": {("employee", "date")},
            },
        ),
    ]
