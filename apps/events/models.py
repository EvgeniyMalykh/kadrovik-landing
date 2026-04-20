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


class NotificationSettings(models.Model):
    """Настройки уведомлений компании — какие типы событий включены."""
    company = models.OneToOneField(
        Company, on_delete=models.CASCADE,
        related_name='notification_settings',
        verbose_name='Компания',
    )
    notify_birthdays = models.BooleanField('Дни рождения', default=True)
    notify_vacations = models.BooleanField('Начало/конец отпусков', default=True)
    notify_probation = models.BooleanField('Испытательный срок', default=True)
    notify_contracts = models.BooleanField('Истечение договоров', default=True)
    notify_subscription = models.BooleanField('Подписка (истечение)', default=True)

    class Meta:
        verbose_name = 'Настройки уведомлений'
        verbose_name_plural = 'Настройки уведомлений'

    def __str__(self):
        return f'Настройки уведомлений — {self.company}'