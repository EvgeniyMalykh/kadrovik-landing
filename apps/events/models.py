from django.db import models
from apps.companies.models import Company
from apps.employees.models import Employee


class HREvent(models.Model):
    class EventType(models.TextChoices):
        CONTRACT_EXPIRY = 'contract_expiry', 'Истекает срочный договор'
        PROBATION_END = 'probation_end', 'Конец испытательного срока'
        VACATION_START = 'vacation_start', 'Начало отпуска'
        VACATION_END = 'vacation_end', 'Конец отпуска'
        BIRTHDAY = 'birthday', 'День рождения'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='events', verbose_name='Компания')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='events', verbose_name='Сотрудник')
    event_type = models.CharField('Тип события', max_length=30, choices=EventType.choices)
    event_date = models.DateField('Дата события')
    notify_days_before = models.PositiveIntegerField('Уведомить за N дней', default=7)
    notified = models.BooleanField('Уведомление отправлено', default=False)
    notified_at = models.DateTimeField('Дата уведомления', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'HR-событие'
        verbose_name_plural = 'HR-события'
        ordering = ['event_date']

    def __str__(self):
        return f'{self.get_event_type_display()} — {self.employee} ({self.event_date})'