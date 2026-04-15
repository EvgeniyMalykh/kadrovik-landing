from django.db import models
from apps.companies.models import Company
from apps.employees.models import Employee


class Document(models.Model):
    class DocType(models.TextChoices):
        HIRE = 'hire', 'Приказ о приёме (Т-1)'
        FIRE = 'fire', 'Приказ об увольнении (Т-8)'
        VACATION = 'vacation', 'Приказ об отпуске (Т-6)'
        TRANSFER = 'transfer', 'Приказ о переводе (Т-5)'
        SALARY_CHANGE = 'salary_change', 'Изменение оклада'
        REFERENCE = 'reference', 'Справка с места работы'
        CONTRACT = 'contract', 'Трудовой договор'
        GPH_CONTRACT = 'gph_contract', 'Договор ГПХ'
        GPH_ACT = 'gph_act', 'Акт выполненных работ'
        TIMESHEET = 'timesheet', 'Табель (Т-13)'
        PERSONAL_CARD = 'personal_card', 'Личная карточка (Т-2)'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='documents', verbose_name='Компания')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents', verbose_name='Сотрудник')
    doc_type = models.CharField('Тип документа', max_length=50, choices=DocType.choices)
    number = models.CharField('Номер приказа', max_length=50)
    date = models.DateField('Дата документа')
    extra_data = models.JSONField('Дополнительные данные', default=dict)
    pdf_file = models.FileField('PDF файл', upload_to='documents/%Y/%m/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Документ'
        verbose_name_plural = 'Документы'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.get_doc_type_display()} — {self.employee} №{self.number}'