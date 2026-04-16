import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
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


def _send_email_to_company(company, subject, html_body, plain_body):
    """Отправляет письмо всем владельцам/администраторам компании."""
    from apps.companies.models import CompanyMember
    emails = list(
        CompanyMember.objects.filter(company=company)
        .values_list("user__email", flat=True)
        .distinct()
    )
    if not emails:
        return
    try:
        send_mail(
            subject=subject,
            message=plain_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            html_message=html_body,
            fail_silently=True,
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
                f"Дата окончания: {emp.probation_end_date.strftime('%d.%m.%Y')}\n\n"
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
                f"Дата окончания договора: {emp.contract_end_date.strftime('%d.%m.%Y')}\n\n"
                f"Подготовьте продление или уведомление об увольнении."
            )
            _send_telegram(text)
    return f"Checked contract endings for {today}"


@shared_task(name="events.check_subscription_expirations")
def check_subscription_expirations():
    """Напоминание об истечении подписки через 3 дня и в день истечения — Telegram + email."""
    from apps.billing.models import Subscription
    today = timezone.now().date()
    notified = 0

    for days_left in [3, 1]:
        target = today + timedelta(days=days_left)
        label = {3: "через 3 дня", 1: "завтра"}[days_left]

        subs = Subscription.objects.filter(
            status="active",
            expires_at__date=target,
        ).select_related("company")

        for sub in subs:
            expires_str = sub.expires_at.strftime("%d.%m.%Y")
            renew_url = "https://app.kadrovik-auto.ru/dashboard/subscription/"

            # --- Telegram (владельцу аккаунта) ---
            tg_text = (
                f"💳 <b>Подписка истекает {label}</b>\n"
                f"Компания: {sub.company.name}\n"
                f"Тариф: {sub.get_plan_display()}\n"
                f"Дата окончания: {expires_str}\n\n"
                f"Продлите подписку: {renew_url}"
            )
            _send_telegram(tg_text)

            # --- Email пользователям компании ---
            subject = f"Подписка «Кадровый автопилот» истекает {label}"
            html_body = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;padding:40px 20px;">
<div style="max-width:520px;margin:0 auto;background:#1e293b;border-radius:12px;padding:36px 32px;color:#f1f5f9;">
  <div style="text-align:center;margin-bottom:24px;">
    <span style="font-size:32px;">💳</span>
    <h1 style="font-size:1.2rem;margin:8px 0 0;">Кадровый автопилот</h1>
  </div>
  <h2 style="font-size:1rem;margin:0 0 12px;color:#fbbf24;">Подписка истекает {label}</h2>
  <p style="color:#94a3b8;font-size:0.9rem;margin:0 0 8px;">
    Компания: <strong style="color:#f1f5f9;">{sub.company.name}</strong>
  </p>
  <p style="color:#94a3b8;font-size:0.9rem;margin:0 0 8px;">
    Тариф: <strong style="color:#f1f5f9;">{sub.get_plan_display()}</strong>
  </p>
  <p style="color:#94a3b8;font-size:0.9rem;margin:0 0 24px;">
    Дата окончания: <strong style="color:#f1f5f9;">{expires_str}</strong>
  </p>
  <p style="color:#94a3b8;font-size:0.85rem;margin:0 0 24px;line-height:1.6;">
    Чтобы не потерять доступ к данным и документам, продлите подписку.
    После истечения данные сохраняются ещё 30 дней.
  </p>
  <div style="text-align:center;margin-bottom:24px;">
    <a href="{renew_url}" style="display:inline-block;background:#3b82f6;color:#fff;padding:13px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:0.95rem;">
      Продлить подписку
    </a>
  </div>
  <p style="color:#64748b;font-size:0.75rem;margin:0;text-align:center;">
    Кадровый автопилот · app.kadrovik-auto.ru
  </p>
</div>
</body></html>"""

            plain_body = (
                f"Подписка «Кадровый автопилот» истекает {label}.\n\n"
                f"Компания: {sub.company.name}\n"
                f"Тариф: {sub.get_plan_display()}\n"
                f"Дата окончания: {expires_str}\n\n"
                f"Продлите подписку: {renew_url}\n\n"
                f"После истечения данные сохраняются ещё 30 дней."
            )

            _send_email_to_company(sub.company, subject, html_body, plain_body)
            notified += 1

    return f"Subscription expiration check for {today}: notified {notified}"
