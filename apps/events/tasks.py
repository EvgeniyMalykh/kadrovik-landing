import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


def _send_telegram(text):
    token   = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


@shared_task(name="events.check_probation_endings")
def check_probation_endings():
    """Напоминание об истечении испытательного срока через 7, 3 и 1 день."""
    from apps.employees.models import Employee
    today = timezone.now().date()
    for days_left in [7, 3, 1]:
        target = today + timedelta(days=days_left)
        employees = Employee.objects.filter(
            probation_end_date=target,
            status="active",
        ).select_related("company")
        for emp in employees:
            label = {7: "через 7 дней", 3: "через 3 дня", 1: "завтра"}[days_left]
            text = (
                f"⚠️ <b>Испытательный срок истекает {label}</b>\n"
                f"Сотрудник: {emp.full_name}\n"
                f"Должность: {emp.position}\n"
                f"Компания: {emp.company.name}\n"
                f"Дата окончания: {emp.probation_end_date.strftime(%d.%m.%Y)}\n\n"
                f"Примите решение: оформить постоянно или уволить."
            )
            _send_telegram(text)
    return f"Checked probation endings for {today}"


@shared_task(name="events.check_contract_endings")
def check_contract_endings():
    """Напоминание об истечении срочного договора через 14, 7 и 3 дня."""
    from apps.employees.models import Employee
    today = timezone.now().date()
    for days_left in [14, 7, 3]:
        target = today + timedelta(days=days_left)
        employees = Employee.objects.filter(
            contract_type="fixed",
            contract_end_date=target,
            status="active",
        ).select_related("company")
        for emp in employees:
            label = {14: "через 14 дней", 7: "через 7 дней", 3: "через 3 дня"}[days_left]
            text = (
                f"📋 <b>Срочный договор истекает {label}</b>\n"
                f"Сотрудник: {emp.full_name}\n"
                f"Должность: {emp.position}\n"
                f"Компания: {emp.company.name}\n"
                f"Дата окончания договора: {emp.contract_end_date.strftime(%d.%m.%Y)}\n\n"
                f"Подготовьте продление или уведомление об увольнении."
            )
            _send_telegram(text)
    return f"Checked contract endings for {today}"


@shared_task(name="events.check_subscription_expirations")
def check_subscription_expirations():
    """Напоминание об истечении подписки через 3 дня."""
    from apps.billing.models import Subscription
    today = timezone.now().date()
    target = today + timedelta(days=3)
    subs = Subscription.objects.filter(
        status="active",
        expires_at__date=target,
    ).select_related("company")
    for sub in subs:
        text = (
            f"💳 <b>Подписка истекает через 3 дня</b>\n"
            f"Компания: {sub.company.name}\n"
            f"Тариф: {sub.get_plan_display()}\n"
            f"Дата окончания: {sub.expires_at.strftime(%d.%m.%Y)}\n\n"
            f"Продлите подписку на app.kadrovik-auto.ru"
        )
        _send_telegram(text)
    return f"Checked subscription expirations for {today}"
