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


@shared_task(name="accounts.send_verification_email_pending")
def send_verification_email_pending(email, verify_url):
    """Отправляет письмо верификации до создания пользователя в БД."""
    subject = "Подтвердите email — Кадровый автопилот"
    html_message = render_to_string("emails/verify_email.html", {
        "verify_url": verify_url,
    })
    plain_message = strip_tags(html_message)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Email send failed for {email}: {e}")


@shared_task(name="accounts.send_password_reset_email")
def send_password_reset_email(email, reset_url):
    """Отправляет письмо со ссылкой сброса пароля."""
    import json
    subject = "Сброс пароля — Кадровый автопилот"
    html_message = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;padding:40px 20px;">
<div style="max-width:520px;margin:0 auto;background:#1e293b;border-radius:12px;padding:36px 32px;color:#f1f5f9;">
  <div style="text-align:center;margin-bottom:24px;">
    <span style="font-size:32px;">&#128203;</span>
    <h1 style="font-size:1.3rem;margin:8px 0 0;">Кадровый автопилот</h1>
  </div>
  <h2 style="font-size:1.1rem;margin:0 0 12px;">Сброс пароля</h2>
  <p style="color:#94a3b8;font-size:0.9rem;margin:0 0 24px;line-height:1.6;">
    Вы запросили сброс пароля для аккаунта <strong style="color:#f1f5f9;">{email}</strong>.<br>
    Нажмите кнопку ниже чтобы задать новый пароль. Ссылка действительна 1 час.
  </p>
  <div style="text-align:center;margin-bottom:24px;">
    <a href="{reset_url}" style="display:inline-block;background:#3b82f6;color:#fff;padding:13px 32px;border-radius:8px;text-decoration:none;font-weight:600;font-size:0.95rem;">
      Задать новый пароль
    </a>
  </div>
  <p style="color:#64748b;font-size:0.78rem;margin:0;line-height:1.5;">
    Если вы не запрашивали смену пароля — просто проигнорируйте это письмо.<br>
    Ссылка: {reset_url}
  </p>
</div>
</body></html>"""

    plain_message = f"Сброс пароля — Кадровый автопилот\n\nПерейдите по ссылке для смены пароля (действительна 1 час):\n{reset_url}\n\nЕсли вы не запрашивали смену пароля — проигнорируйте это письмо."

    try:
        from django.core.mail import send_mail
        from django.conf import settings
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Password reset email failed for {email}: {e}")
