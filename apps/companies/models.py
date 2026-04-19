import uuid

from django.db import models
from django.conf import settings
from django.utils import timezone


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
    sfr_reg_number = models.CharField("Рег. номер СФР", max_length=20, blank=True)
    okved = models.CharField("ОКВЭД", max_length=10, blank=True)
    legal_address = models.TextField('Юридический адрес')
    actual_address = models.TextField('Фактический адрес', blank=True)
    director_name = models.CharField('ФИО руководителя', max_length=255)
    director_position = models.CharField('Должность руководителя', max_length=255, default='Директор')
    phone = models.CharField('Телефон', max_length=20, blank=True)
    email = models.EmailField('Email', blank=True)
    MESSENGER_CHOICES = [
        ('email', 'Email'),
        ('telegram', 'Telegram'),
        ('whatsapp', 'WhatsApp'),
        ('viber', 'Viber'),
    ]
    notify_messenger = models.CharField(
        'Мессенджер для уведомлений',
        max_length=20,
        choices=MESSENGER_CHOICES,
        default='email',
        blank=True
    )
    notify_contact = models.CharField(
        'Контакт для уведомлений',
        max_length=255,
        blank=True,
        help_text='Email, номер телефона или @username в Telegram'
    )
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


class CompanyInvite(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Администратор'
        HR = 'hr', 'Кадровик'
        ACCOUNTANT = 'accountant', 'Бухгалтер'

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='invites')
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_invites')
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.HR)
    accepted = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Приглашение'
        verbose_name_plural = 'Приглашения'
        unique_together = ('company', 'email')

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.email} → {self.company.name}"