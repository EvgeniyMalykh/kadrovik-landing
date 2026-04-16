import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def _send_telegram(text):
    token   = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', '')
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


def _send_google_sheets(email, company_name, registered_at):
    gas_url = getattr(settings, 'GAS_URL', '')
    if not gas_url:
        return
    try:
        requests.post(
            gas_url,
            json={
                "action": "new_user",
                "email": email,
                "company": company_name,
                "date": registered_at,
            },
            timeout=15,
        )
    except Exception:
        pass


@shared_task(name="accounts.send_verification_email")
def send_verification_email(user_id, verify_url):
    """Отправляет письмо с ссылкой подтверждения email."""
    from apps.accounts.models import User
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return

    subject = "Подтвердите email — Кадровый автопилот"
    html_message = render_to_string("emails/verify_email.html", {
        "user": user,
        "verify_url": verify_url,
    })
    plain_message = strip_tags(html_message)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Email send failed for {user.email}: {e}")


@shared_task(name="accounts.notify_new_registration")
def notify_new_registration(email, company_name, registered_at):
    """Telegram + Google Sheets при новой регистрации."""
    text = (
        f"🎉 <b>Новая регистрация!</b>\n"
        f"📧 Email: <code>{email}</code>\n"
        f"🏢 Компания: {company_name}\n"
        f"🕐 Дата: {registered_at}"
    )
    _send_telegram(text)
    _send_google_sheets(email, company_name, registered_at)
