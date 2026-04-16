from django.db import models
from django.conf import settings


class Company(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='companies',
        verbose_name='Владелец'
    )
    name = models.CharField('Название', max_length=255)
    inn = models.CharField('ИНН', max_length=12)
    ogrn = models.CharField('ОГРН', max_length=15, blank=True)
    kpp = models.CharField('КПП', max_length=9, blank=True)
    okpo = models.CharField('ОКПО', max_length=10, blank=True)
    legal_address = models.TextField('Юридический адрес')
    actual_address = models.TextField('Фактический адрес', blank=True)
    director_name = models.CharField('ФИО руководителя', max_length=255)
    director_position = models.CharField('Должность руководителя', max_length=255, default='Директор')
    phone = models.CharField('Телефон', max_length=20, blank=True)
    email = models.EmailField('Email', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Компания'
        verbose_name_plural = 'Компании'

    def __str__(self):
        return self.name


class CompanyMember(models.Model):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Владелец'
        ADMIN = 'admin', 'Администратор'
        HR = 'hr', 'Кадровик'
        ACCOUNTANT = 'accountant', 'Бухгалтер'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField('Роль', max_length=20, choices=Role.choices, default=Role.HR)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Участник компании'
        verbose_name_plural = 'Участники компании'
        unique_together = ('company', 'user')

    def __str__(self):
        return f'{self.user} — {self.company} ({self.get_role_display()})'