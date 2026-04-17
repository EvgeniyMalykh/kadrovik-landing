"""
Celery-задачи для автопродления подписок через ЮКассу.
Запускается ежедневно через django-celery-beat.
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name="billing.renew_expiring_subscriptions")
def renew_expiring_subscriptions():
    """
    Ежедневно проверяет подписки, истекающие через 3 дня,
    и запускает автосписание если сохранён payment_method_id.
    """
    from apps.billing.models import Subscription
    from apps.billing.services import create_recurring_payment

    now = timezone.now()
    renew_before = now + timedelta(days=3)

    # Подписки с автопродлением, истекающие в ближайшие 3 дня
    subs = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        auto_renew=True,
        expires_at__lte=renew_before,
        expires_at__gte=now,
        payment_method_id__isnull=False,
    ).exclude(payment_method_id='').select_related('company')

    logger.info(f"[billing] Проверка автопродления: найдено {subs.count()} подписок")

    for sub in subs:
        try:
            payment = create_recurring_payment(sub.company, sub.plan)
            if payment:
                logger.info(f"[billing] Автосписание запущено: company={sub.company_id}, payment={payment.id}")
        except Exception as e:
            logger.error(f"[billing] Ошибка автосписания company={sub.company_id}: {e}")

    return f"Обработано: {subs.count()} подписок"
