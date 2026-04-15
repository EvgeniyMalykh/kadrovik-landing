from django.db import models
from apps.companies.models import Company


class HREvent(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=255)
    event_date = models.DateField()
    remind_at = models.DateTimeField(null=True, blank=True)
