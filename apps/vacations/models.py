from django.db import models
from apps.employees.models import Employee
from apps.documents.models import Document


class Vacation(models.Model):
    class VacationType(models.TextChoices):
        ANNUAL = 'annual', 'Ежегодный оплачиваемый'
        UNPAID = 'unpaid', 'За свой счёт (без сохранения зарплаты)'
        MATERNITY = 'maternity', 'Декретный'
        EDUCATIONAL = 'educational', 'Учебный'

    employee     = models.ForeignKey(Employee, on_delete=models.CASCADE,
                                     related_name='vacations', verbose_name='Сотрудник')
    vacation_type = models.CharField('Тип отпуска', max_length=20,
                                     choices=VacationType.choices, default=VacationType.ANNUAL)
    start_date   = models.DateField('Дата начала')
    end_date     = models.DateField('Дата окончания')
    days_count   = models.PositiveIntegerField('Количество дней', default=0)
    reason       = models.TextField('Причина / основание', blank=True, default='')
    approved     = models.BooleanField('Согласован', default=False)
    document     = models.OneToOneField(Document, on_delete=models.SET_NULL,
                                         null=True, blank=True, verbose_name='Приказ')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Отпуск / заявление'
        verbose_name_plural = 'Отпуска / заявления'
        ordering = ['-start_date']

    def __str__(self):
        return (f'{self.employee} — {self.get_vacation_type_display()} '
                f'({self.start_date} — {self.end_date})')

    def save(self, *args, **kwargs):
        if self.start_date and self.end_date:
            self.days_count = (self.end_date - self.start_date).days + 1
        super().save(*args, **kwargs)
