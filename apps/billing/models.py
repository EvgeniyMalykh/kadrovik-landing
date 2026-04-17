from django.db import models
from apps.companies.models import Company


class Subscription(models.Model):
    class Plan(models.TextChoices):
        TRIAL    = 'trial',    'Пробный'
        START    = 'start',    'Старт'
        BUSINESS = 'business', 'Бизнес'
        PRO      = 'pro',      'Корпоратив'

    class Status(models.TextChoices):
        ACTIVE    = 'active',    'Активна'
        EXPIRED   = 'expired',   'Истекла'
        CANCELLED = 'cancelled', 'Отменена'

    company       = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='subscription')
    plan          = models.CharField('Тариф', max_length=20, choices=Plan.choices, default=Plan.TRIAL)
    status        = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.ACTIVE)
    started_at    = models.DateTimeField(auto_now_add=True)
    expires_at         = models.DateTimeField('Истекает', null=True, blank=True)
    max_employees      = models.PositiveIntegerField('Макс. сотрудников', default=10)
    # Рекуррентные платежи
    payment_method_id  = models.CharField('ИД метода оплаты (рекуррент)', max_length=255, blank=True, default='')
    auto_renew         = models.BooleanField('Автопродление', default=False)

    class Meta:
        verbose_name = 'Подписка'
        verbose_name_plural = 'Подписки'

    def __str__(self):
        return f'{self.company} — {self.get_plan_display()}'

    @property
    def is_active(self):
        from django.utils import timezone
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING  = 'pending',  'Ожидает'
        SUCCESS  = 'success',  'Успешно'
        FAILED   = 'failed',   'Ошибка'
        REFUNDED = 'refunded', 'Возврат'

    company            = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payments')
    plan               = models.CharField('Тариф', max_length=20, default='start')
    amount             = models.DecimalField('Сумма', max_digits=10, decimal_places=2)
    status             = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.PENDING)
    yukassa_payment_id = models.CharField('ID платежа ЮKassa', max_length=255, blank=True)
    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Платёж'
        verbose_name_plural = 'Платежи'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.company} — {self.amount} ₽ ({self.get_status_display()})'
