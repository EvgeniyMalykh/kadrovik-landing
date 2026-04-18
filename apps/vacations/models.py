from django.db import models
from apps.employees.models import Employee
from apps.documents.models import Document
from apps.companies.models import Company


class Vacation(models.Model):
    class VacationType(models.TextChoices):
        ANNUAL = 'annual', 'Ежегодный оплачиваемый'
        ADDITIONAL = 'additional', 'Дополнительный оплачиваемый'
        UNPAID = 'unpaid', 'За свой счёт (без сохранения зарплаты)'
        MATERNITY = 'maternity', 'По беременности и родам'
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


class VacationSchedule(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='vacation_schedules')
    year = models.IntegerField(verbose_name='Год')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Последнее обновление')

    class Meta:
        unique_together = [['company', 'year']]
        verbose_name = 'График отпусков'
        verbose_name_plural = 'Графики отпусков'

    def __str__(self):
        return f'{self.company.name} — {self.year}'


class VacationScheduleEntry(models.Model):
    schedule = models.ForeignKey(VacationSchedule, on_delete=models.CASCADE, related_name='entries')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='vacation_schedule_entries')
    days_total = models.IntegerField(default=28, verbose_name='Дней положено')

    period1_start = models.DateField(null=True, blank=True, verbose_name='Период 1 начало')
    period1_end = models.DateField(null=True, blank=True, verbose_name='Период 1 конец')
    period2_start = models.DateField(null=True, blank=True, verbose_name='Период 2 начало')
    period2_end = models.DateField(null=True, blank=True, verbose_name='Период 2 конец')
    period3_start = models.DateField(null=True, blank=True, verbose_name='Период 3 начало')
    period3_end = models.DateField(null=True, blank=True, verbose_name='Период 3 конец')

    # Северный отпуск
    days_north = models.IntegerField(default=0, verbose_name='Северный отпуск (дней)')
    north_start = models.DateField(null=True, blank=True, verbose_name='Северный отпуск начало')
    north_end = models.DateField(null=True, blank=True, verbose_name='Северный отпуск конец')

    # Дополнительный отпуск
    days_extra = models.IntegerField(default=0, verbose_name='Доп. отпуск (дней)')
    extra_start = models.DateField(null=True, blank=True, verbose_name='Доп. отпуск начало')
    extra_end = models.DateField(null=True, blank=True, verbose_name='Доп. отпуск конец')

    @property
    def days_used(self):
        total = 0
        for (s, e) in [
            (self.period1_start, self.period1_end),
            (self.period2_start, self.period2_end),
            (self.period3_start, self.period3_end),
            (self.north_start, self.north_end),
            (self.extra_start, self.extra_end),
        ]:
            if s and e:
                total += (e - s).days + 1
        return total

    @property
    def days_total_all(self):
        return self.days_total + self.days_north + self.days_extra

    @property
    def days_remaining(self):
        return self.days_total_all - self.days_used

    class Meta:
        verbose_name = 'Запись графика отпусков'
        verbose_name_plural = 'Записи графика отпусков'
        ordering = ['employee__last_name']

    def __str__(self):
        return f'{self.employee.full_name} — {self.schedule.year}'
