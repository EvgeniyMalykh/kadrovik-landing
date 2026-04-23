import logging
import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def _send_telegram(text):
    """Отправляет уведомление через Green API Telegram (api.telegram.org заблокирован на VPS)."""
    import re as _re
    instance_id = getattr(settings, "GREEN_API_TG_INSTANCE_ID", "")
    tg_token    = getattr(settings, "GREEN_API_TG_TOKEN", "")
    chat_id     = str(getattr(settings, "TELEGRAM_CHAT_ID", "") or "").strip()
    if not chat_id:
        return
    plain_text = _re.sub(r"<[^>]+>", "", str(text)).strip()
    if instance_id and tg_token:
        # Green API требует chatId в формате: номер@c.us (для Telegram) или LID
        tg_chat_id = chat_id if "@" in chat_id else f"{chat_id}@c.us"
        try:
            resp = requests.post(
                f"https://api.green-api.com/waInstance{instance_id}/sendMessage/{tg_token}",
                json={"chatId": tg_chat_id, "message": plain_text},
                timeout=10,
            )
            logger.info(f"Green API TG response: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Green API TG error: {e}")
    else:
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if not token:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": plain_text},
                timeout=10,
            )
        except Exception:
            pass


def _send_google_sheets(email, company_name, registered_at, display_name='', telegram='', employee_count=0):
    """Записывает данные в Google Sheets.
    
    Приоритет:
    1. gspread (Service Account) — надёжно, не зависит от VPS IP
    2. GAS webhook — fallback, работает если Google не блокирует IP
    """
    # Попытка через gspread (Service Account)
    gs_creds_json = getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_JSON', '')
    gs_sheet_id   = getattr(settings, 'GOOGLE_SHEET_ID', '1JS9iTtGaBCC2ElW-BaGRiLZh10-T8F8NJF6_ZLMdewg')
    if gs_creds_json:
        try:
            import json
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive',
            ]
            creds_dict = json.loads(gs_creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(gs_sheet_id)
            worksheet = sh.worksheet('Лист1')
            worksheet.append_row([
                registered_at,
                display_name or company_name,
                email,
                telegram or '',
                str(employee_count) if employee_count else '',
                'Регистрация',
            ])
            logger.info(f"gspread: записан пользователь {email}")
            return
        except ImportError:
            logger.warning("gspread не установлен, пробуем GAS")
        except Exception as e:
            logger.error(f"gspread error: {e}")

    # Fallback: GAS webhook
    gas_url = getattr(settings, 'GAS_URL', '')
    if not gas_url:
        return
    try:
        resp = requests.post(
            gas_url,
            json={
                "action": "new_user",
                "email": email,
                "company": company_name,
                "date": registered_at,
                "name": display_name or company_name,
                "telegram": telegram,
                "employees": employee_count,
                "source": "Регистрация",
            },
            timeout=15,
            allow_redirects=True,
        )
        logger.info(f"GAS response: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.error(f"GAS error: {e}")


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
        logger.error(f"Email send failed for {user.email}: {e}")


@shared_task(name="accounts.notify_new_registration")
def notify_new_registration(email, company_name, registered_at, display_name='', telegram='', employee_count=0):
    """Telegram + Google Sheets при новой регистрации."""
    text = (
        f"🎉 Новая регистрация!\n"
        f"📧 Email: {email}\n"
        f"👤 Имя: {display_name or company_name}\n"
        f"🏢 Компания: {company_name}\n"
        f"💬 Telegram: {telegram or '—'}\n"
        f"👥 Сотрудников: {employee_count or '—'}\n"
        f"🕐 Дата: {registered_at}"
    )
    _send_telegram(text)
    _send_google_sheets(email, company_name, registered_at, display_name, telegram, employee_count)


@shared_task(name="accounts.send_verification_email_pending")
def send_verification_email_pending(email, verify_url):
    """Отправляет письмо верификации до создания пользователя в БД."""
    subject = "Подтвердите email — Кадровый автопилот"
    html_message = render_to_string("emails/verify_email.html", {
        "verify_url": verify_url,
    })
    plain_message = strip_tags(html_message)

    try:
        reply_to = getattr(settings, "REPLY_TO_EMAIL", None)
        from django.core.mail import EmailMultiAlternatives
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
            reply_to=[reply_to] if reply_to else None,
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)
    except Exception as e:
        logger.error(f"Email send failed for {email}: {e}")


@shared_task(name="accounts.send_password_reset_email")
def send_password_reset_email(email, reset_url):
    """Отправляет письмо со ссылкой сброса пароля."""
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
        reply_to = getattr(settings, "REPLY_TO_EMAIL", None)
        from django.core.mail import EmailMultiAlternatives
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
            reply_to=[reply_to] if reply_to else None,
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)
    except Exception as e:
        logger.error(f"Password reset email failed for {email}: {e}")
