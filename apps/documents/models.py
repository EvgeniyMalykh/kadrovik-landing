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
        DISMISSAL = 'dismissal', 'Приказ об увольнении'
        BONUS = 'bonus', 'Приказ о премии'
        DISCIPLINARY = 'disciplinary', 'Приказ о дисциплинарном взыскании'
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

import os

DOC_TYPES = [
    ('hire', 'Приказ о приёме (Т-1)'),
    ('personal_card', 'Личная карточка (Т-2)'),
    ('transfer', 'Приказ о переводе (Т-5)'),
    ('vacation', 'Приказ об отпуске (Т-6)'),
    ('fire', 'Приказ об увольнении (Т-8)'),
    ('contract', 'Трудовой договор'),
    ('gph_contract', 'Договор ГПХ'),
    ('gph_act', 'Акт выполненных работ'),
    ('reference', 'Справка с места работы'),
    ('bonus', 'Приказ о премии'),
    ('disciplinary', 'Приказ о дисциплинарном взыскании'),
    ('salary_change', 'Изменение оклада'),
    ('dismissal', 'Приказ об увольнении'),
]


def template_upload_path(instance, filename):
    return f'document_templates/{instance.company_id}/{instance.doc_type}/{filename}'


class DocumentTemplate(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='document_templates')
    doc_type = models.CharField('Тип документа', max_length=50, choices=DOC_TYPES)
    file = models.FileField('Файл шаблона', upload_to=template_upload_path)
    name = models.CharField('Название файла', max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'doc_type')
        verbose_name = 'Шаблон документа'
        verbose_name_plural = 'Шаблоны документов'

    def __str__(self):
        return f"{self.get_doc_type_display()} — {self.company.name}"

    def delete(self, *args, **kwargs):
        if self.file and os.path.isfile(self.file.path):
            os.remove(self.file.path)
        super().delete(*args, **kwargs)
