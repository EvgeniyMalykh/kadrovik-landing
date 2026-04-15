from django.db import models
from apps.companies.models import Company
from apps.employees.models import Employee


class Document(models.Model):
    class Type(models.TextChoices):
        EMPLOYMENT_CONTRACT = 'employment_contract', 'Employment Contract'
        ORDER_HIRE = 'order_hire', 'Order Hire'
        ORDER_DISMISSAL = 'order_dismissal', 'Order Dismissal'
        ORDER_VACATION = 'order_vacation', 'Order Vacation'
        TIMESHEET = 'timesheet', 'Timesheet'
        PERSONAL_CARD = 'personal_card', 'Personal Card'
        PAYROLL = 'payroll', 'Payroll'
        NDA = 'nda', 'NDA'
        POLICY = 'policy', 'Policy'
        INSTRUCTION = 'instruction', 'Instruction'
        OTHER = 'other', 'Other'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='documents')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    type = models.CharField(max_length=50, choices=Type.choices)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
