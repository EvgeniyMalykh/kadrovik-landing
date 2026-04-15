from django.db import models
from apps.employees.models import Employee


class Vacation(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='vacations')
    start_date = models.DateField()
    end_date = models.DateField()
    approved = models.BooleanField(default=False)
