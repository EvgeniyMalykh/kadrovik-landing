from django.db import models
from apps.companies.models import Company


class Department(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField('Название отдела', max_length=255)

    class Meta:
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'

    def __str__(self):
        return f'{self.company} — {self.name}'


class Employee(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Работает'
        FIRED = 'fired', 'Уволен'
        ON_LEAVE = 'on_leave', 'В отпуске'
        ON_SICK = 'on_sick', 'На больничном'

    class ContractType(models.TextChoices):
        PERMANENT = 'permanent', 'Бессрочный'
        FIXED = 'fixed', 'Срочный'
        GPH = 'gph', 'ГПХ'

    # Основное
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees', verbose_name='Компания')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Отдел')
    last_name = models.CharField('Фамилия', max_length=100)
    first_name = models.CharField('Имя', max_length=100)
    middle_name = models.CharField('Отчество', max_length=100, blank=True)
    position = models.CharField('Должность', max_length=255)
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.ACTIVE)

    # Трудовой договор
    hire_date = models.DateField('Дата приёма')
    fire_date = models.DateField('Дата увольнения', null=True, blank=True)
    contract_type = models.CharField('Тип договора', max_length=20, choices=ContractType.choices, default=ContractType.PERMANENT)
    contract_end_date = models.DateField('Дата окончания договора', null=True, blank=True)
    probation_end_date = models.DateField('Конец испытательного срока', null=True, blank=True)
    salary = models.DecimalField('Оклад', max_digits=12, decimal_places=2, null=True, blank=True, default=0)
    personnel_number = models.CharField('Табельный номер', max_length=20, blank=True)

    # Паспортные данные
    passport_series = models.CharField('Серия паспорта', max_length=4, blank=True)
    passport_number = models.CharField('Номер паспорта', max_length=6, blank=True)
    passport_issued_by = models.TextField('Кем выдан', blank=True)
    passport_issued_date = models.DateField('Дата выдачи', null=True, blank=True)
    passport_registration = models.TextField('Адрес регистрации', blank=True)

    # ИНН / СНИЛС
    inn = models.CharField('ИНН', max_length=12, blank=True)
    snils = models.CharField('СНИЛС', max_length=14, blank=True)

    # Контакты
    phone = models.CharField('Телефон', max_length=20, blank=True)
    email = models.EmailField('Email', blank=True)
    birth_date = models.DateField('Дата рождения', null=True, blank=True)
    birth_place = models.CharField(max_length=255, blank=True, default='', verbose_name='Место рождения')
    education = models.CharField(
        max_length=50,
        choices=[
            ('', '—'),
            ('secondary', 'Среднее'),
            ('secondary_special', 'Среднее специальное'),
            ('incomplete_higher', 'Неполное высшее'),
            ('higher', 'Высшее'),
            ('two_higher', 'Два высших'),
            ('postgraduate', 'Аспирантура / учёная степень'),
        ],
        blank=True, default='', verbose_name='Образование'
    )
    MARITAL_STATUS_CHOICES = [
        ('single', 'Не женат / Не замужем'),
        ('married', 'Женат / Замужем'),
        ('divorced', 'Разведён / Разведена'),
        ('widowed', 'Вдовец / Вдова'),
        ('cohabiting', 'Гражданский брак'),
    ]
    marital_status = models.CharField(
        max_length=20,
        choices=MARITAL_STATUS_CHOICES,
        blank=True,
        null=True,
        verbose_name='Семейное положение'
    )
    citizenship = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Гражданство',
        default='Российская Федерация'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return ' '.join(p for p in parts if p)

    @property
    def short_name(self):
        parts = [self.last_name]
        if self.first_name:
            parts.append(f'{self.first_name[0]}.')
        if self.middle_name:
            parts.append(f'{self.middle_name[0]}.')
        return ' '.join(parts)

class SalaryHistory(models.Model):
    employee = models.ForeignKey(
        'Employee', on_delete=models.CASCADE,
        related_name='salary_history', verbose_name='Сотрудник'
    )
    salary = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name='Оклад'
    )
    effective_date = models.DateField(
        verbose_name='Дата вступления в силу'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_date', '-created_at']
        verbose_name = 'История оклада'
        verbose_name_plural = 'История окладов'

    def __str__(self):
        return f"{self.employee} — {self.salary} с {self.effective_date}"


class TimeRecord(models.Model):
    """Ручная отметка в табеле Т-13."""
    class Code(models.TextChoices):
        WORK      = 'Я',  'Явка (рабочий день)'
        VACATION  = 'ОТ', 'Отпуск ежегодный'
        VACATION_U= 'ДО', 'Отпуск доп.'
        VACATION_STUDY = 'УЧ', 'Учебный отпуск'
        VACATION_MATERNITY = 'ОЖ', 'Отпуск по беременности и родам'
        SICK      = 'Б',  'Больничный'
        HOLIDAY   = 'П',  'Праздник'
        WEEKEND   = 'В',  'Выходной'
        TRIP      = 'К',  'Командировка'
        ABSENT    = 'НН', 'Неявка невыясненная'
        HALF      = 'Я½', 'Неполный день'
        DAYOFF_WORK = 'РВ', 'Работа в выходной'
        OVERTIME  = 'Я/С', 'Сверхурочные'

    employee  = models.ForeignKey(Employee, on_delete=models.CASCADE,
                                   related_name='time_records', verbose_name='Сотрудник')
    date      = models.DateField('Дата')
    code      = models.CharField('Код', max_length=3, choices=Code.choices, default=Code.WORK)
    hours     = models.PositiveSmallIntegerField('Часов', default=8)

    class Meta:
        verbose_name = 'Отметка табеля'
        verbose_name_plural = 'Отметки табеля'
        unique_together = ('employee', 'date')
        ordering = ['date']

    def __str__(self):
        return f'{self.employee.full_name} {self.date} — {self.code}'


class ProductionCalendar(models.Model):
    """Производственный календарь РФ — праздники и сокращённые дни."""
    DAY_TYPE_CHOICES = [
        ('holiday', 'Праздничный/выходной'),
        ('short', 'Предпраздничный сокращённый'),
    ]
    date = models.DateField('Дата', unique=True)
    day_type = models.CharField('Тип дня', max_length=20, choices=DAY_TYPE_CHOICES)
    description = models.CharField('Описание', max_length=200, blank=True)

    class Meta:
        ordering = ['date']
        verbose_name = 'Производственный календарь'
        verbose_name_plural = 'Производственный календарь'

    def __str__(self):
        return f'{self.date} — {self.get_day_type_display()}'
