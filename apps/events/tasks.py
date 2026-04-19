import logging
import re
import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


def _send_telegram(text, chat_id=None):
    """Отправляет сообщение в Telegram через Green API TG-инстанс.
    Прямой api.telegram.org заблокирован провайдером VPS — используем Green API.
    """
    instance_id = getattr(settings, 'GREEN_API_TG_INSTANCE_ID', '')
    tg_token    = getattr(settings, 'GREEN_API_TG_TOKEN', '')

    target = chat_id or getattr(settings, 'TELEGRAM_CHAT_ID', None)
    if not target:
        return

    # Убираем HTML-теги: Green API Telegram не поддерживает parse_mode
    plain_text = re.sub(r'<[^>]+>', '', str(text)).strip()

    if instance_id and tg_token:
        # Green API Telegram: chatId должен быть числовым ID (username не поддерживается)
        target_str = str(target).strip().lstrip('@')
        # Проверяем что это числовой ID (может быть отрицательным для групп)
        clean = target_str.lstrip('-')
        if not clean.isdigit():
            raise ValueError(
                f"Telegram: укажите числовой ID чата, а не username. "
                f"Узнать ID можно через бот @userinfobot — напишите ему /start."
            )
        green_chat_id = target_str
        _green_api_send(instance_id, tg_token, green_chat_id, plain_text)
    else:
        # Fallback: прямой Telegram Bot API (для локальной разработки)
        direct_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not direct_token:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{direct_token}/sendMessage",
                json={"chat_id": target, "text": plain_text},
                timeout=10,
            )
        except Exception:
            pass

def _resolve_telegram_chat_id(contact):
    """Получает Telegram chat_id по username через getChat API."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not contact:
        return None
    username = contact.strip().lstrip('@')
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getChat",
            params={"chat_id": f"@{username}"},
            timeout=10,
        )
        data = r.json()
        if data.get('ok'):
            return data['result']['id']
    except Exception:
        pass
    return None



def _green_api_send(instance_id: str, token: str, chat_id: str, text: str):
    """Универсальная отправка через Green API (sendMessage)."""
    url = f'https://api.green-api.com/waInstance{instance_id}/sendMessage/{token}'
    payload = {'chatId': chat_id, 'message': text}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.info(f'Green API sent to {chat_id}: {resp.status_code}')
    except Exception as e:
        logger.error(f'Green API error (instance {instance_id}): {e}')


def _normalize_phone(phone: str) -> str:
    """Нормализует номер телефона → только цифры, начиная с 7."""
    import re
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]
    return digits


def _send_whatsapp(phone: str, text: str):
    """Отправляет сообщение в WhatsApp через Green API WA-инстанс."""
    instance_id = getattr(settings, 'GREEN_API_WA_INSTANCE_ID', '')
    token = getattr(settings, 'GREEN_API_WA_TOKEN', '')
    if not instance_id or not token:
        logger.warning('GREEN_API_WA не настроен — пропускаем WhatsApp уведомление')
        return
    digits = _normalize_phone(phone)
    chat_id = digits + '@c.us'
    _green_api_send(instance_id, token, chat_id, text)


def _send_max(phone_or_id: str, text: str):
    """Отправляет сообщение в Max (ВКонтакте Мессенджер) через Green API Max-инстанс.
    phone_or_id — номер телефона или userId.
    """
    instance_id = getattr(settings, 'GREEN_API_MAX_INSTANCE_ID', '')
    token = getattr(settings, 'GREEN_API_MAX_TOKEN', '')
    if not instance_id or not token:
        logger.warning('GREEN_API_MAX не настроен — пропускаем Max уведомление')
        return
    # Max использует chatId = номер@c.us или userId@c.us
    digits = _normalize_phone(phone_or_id)
    chat_id = (digits + '@c.us') if digits else (phone_or_id.lstrip('+') + '@c.us')
    _green_api_send(instance_id, token, chat_id, text)


def _send_email_to_company(company, subject, html_body, plain_body):
    """Отправляет письмо. Если notify_messenger=email и notify_contact заполнен —
    шлём туда. Иначе fallback на company.email / owner.email."""
    if company.notify_messenger == 'email' and company.notify_contact:
        recipient = company.notify_contact
    else:
        recipient = company.email or getattr(company.owner, 'email', None)
    if not recipient:
        return
    try:
        send_mail(
            subject=subject,
            message=plain_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=html_body,
            fail_silently=True,
        )
    except Exception:
        pass


def _get_contact_for_messenger(company, messenger):
    """Возвращает контакт для конкретного мессенджера из отдельных полей (с fallback на notify_contact)."""
    field_map = {
        'email':    'notify_email_contact',
        'telegram': 'notify_telegram_contact',
        'whatsapp': 'notify_whatsapp_contact',
        'viber':    'notify_viber_contact',
        'max':      'notify_max_contact',
    }
    field = field_map.get(messenger)
    if field:
        val = getattr(company, field, '') or ''
        if val.strip():
            return val.strip()
    # Fallback: старое единое поле
    return (company.notify_contact or '').strip()


def _send_notification_to_company(company, text, subject, html_body, plain_body):
    """Универсальный роутер: шлёт уведомление через канал, выбранный в карточке компании."""
    messenger = company.notify_messenger or 'email'
    contact = _get_contact_for_messenger(company, messenger)

    if messenger == 'telegram':
        if contact:
            _send_telegram(text, chat_id=contact)
        else:
            _send_telegram(text)
    elif messenger == 'email':
        _send_email_to_company(company, subject, html_body, plain_body)
    elif messenger == 'whatsapp':
        if contact:
            _send_whatsapp(contact, text)
        else:
            _send_email_to_company(company, subject, html_body, plain_body)
    elif messenger == 'viber':
        # Viber пока не реализован — fallback на email
        _send_email_to_company(company, subject, html_body, plain_body)
    elif messenger == 'max':
        if contact:
            _send_max(contact, text)
        else:
            _send_email_to_company(company, subject, html_body, plain_body)
    else:
        # Viber и прочие — fallback на email
        _send_email_to_company(company, subject, html_body, plain_body)


def _has_email_notify(company):
    """Проверяет, доступна ли фича email_notify для плана компании."""
    from apps.billing.services import get_plan_features
    sub = getattr(company, 'subscription', None)
    plan_key = sub.plan if sub else 'start'
    features = get_plan_features(plan_key)
    return features.get('email_notify', False)


def _send_hr_email(company, icon, title, employee_name, position, event_date, description):
    """Отправляет HR-уведомление через канал, выбранный в карточке компании."""
    subject = title
    context = {
        'icon': icon,
        'title': title,
        'employee_name': employee_name,
        'position': position,
        'company_name': company.name,
        'event_date': event_date,
        'description': description,
    }
    html_body = render_to_string('emails/hr_event.html', context)
    nl = '\n'
    plain_body = (
        title + nl + nl
        + 'Сотрудник: ' + employee_name + nl
        + 'Должность: ' + position + nl
        + 'Компания: ' + company.name + nl
        + 'Дата: ' + event_date + nl + nl
        + description
    )
    text = (
        icon + ' <b>' + title + '</b>' + nl
        + 'Сотрудник: ' + employee_name + nl
        + 'Должность: ' + position + nl
        + 'Компания: ' + company.name + nl
        + 'Дата: ' + event_date + nl + nl
        + description
    )
    _send_notification_to_company(company, text, subject, html_body, plain_body)

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

            # Email-уведомление (если доступно по плану)
            if _has_email_notify(emp.company):
                _send_hr_email(
                    company=emp.company,
                    icon='⚠️',
                    title=f'Испытательный срок истекает {label}',
                    employee_name=emp.full_name,
                    position=emp.position,
                    event_date=emp.probation_end_date.strftime('%d.%m.%Y'),
                    description='Примите решение: оформить сотрудника на постоянную основу или подготовить документы на увольнение.',
                )
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

            # Email-уведомление (если доступно по плану)
            if _has_email_notify(emp.company):
                _send_hr_email(
                    company=emp.company,
                    icon='📋',
                    title=f'Срочный договор истекает {label}',
                    employee_name=emp.full_name,
                    position=emp.position,
                    event_date=emp.contract_end_date.strftime('%d.%m.%Y'),
                    description='Подготовьте продление договора или уведомление сотрудника об увольнении.',
                )
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


@shared_task(name="events.check_birthdays")
def check_birthdays():
    """Уведомлять за 3 дня и в день рождения сотрудника."""
    from apps.employees.models import Employee
    from apps.companies.models import Company

    today = timezone.now().date()
    notify_days = [0, 3]  # в день рождения и за 3 дня
    notified = 0

    for company in Company.objects.all():
        employees = Employee.objects.filter(company=company, status='active')

        messages = []
        email_items = []
        for emp in employees:
            if not emp.birth_date:
                continue
            try:
                bday_this_year = emp.birth_date.replace(year=today.year)
            except ValueError:
                continue  # 29 февраля в не-високосный год

            days_until = (bday_this_year - today).days
            if days_until not in notify_days:
                continue

            age = today.year - emp.birth_date.year
            if days_until == 0:
                text = (
                    f"🎂 <b>Сегодня день рождения</b>\n"
                    f"Сотрудник: {emp.full_name}\n"
                    f"Исполняется {age} лет"
                )
                description = f'Исполняется {age} лет'
            else:
                text = (
                    f"🎂 <b>Через {days_until} дня день рождения</b>\n"
                    f"Сотрудник: {emp.full_name}\n"
                    f"Исполняется {age} лет"
                )
                description = f'Через {days_until} дня, исполняется {age} лет'

            messages.append(text)
            email_items.append((emp, description, bday_this_year, days_until))

        if not messages:
            continue

        # Telegram
        try:
            _send_telegram('\n\n'.join(messages))
        except Exception as e:
            logger.error(f'Birthday Telegram error company {company.id}: {e}')

        # Email (если тариф позволяет)
        if _has_email_notify(company):
            for emp, description, bday, days_until in email_items:
                try:
                    title = 'Сегодня день рождения сотрудника' if days_until == 0 else 'Скоро день рождения сотрудника'
                    _send_hr_email(
                        company=company,
                        icon='🎂',
                        title=title,
                        employee_name=emp.full_name,
                        position=emp.position or '',
                        event_date=bday.strftime('%d.%m.%Y'),
                        description=description,
                    )
                except Exception as e:
                    logger.error(f'Birthday email error: {e}')

        notified += len(messages)

    return f"Birthday check for {today}: notified {notified}"


@shared_task(name="events.check_vacation_events")
def check_vacation_events():
    """Уведомлять за 1 день до начала и в день начала отпуска."""
    from apps.vacations.models import Vacation
    from apps.companies.models import Company

    today = timezone.now().date()
    notified = 0

    for company in Company.objects.all():
        vacations = Vacation.objects.filter(
            employee__company=company,
            employee__status='active',
            start_date__in=[today, today + timedelta(days=1)],
        ).select_related('employee')

        if not vacations.exists():
            continue

        vac_type_map = {
            'annual': 'Ежегодный отпуск',
            'unpaid': 'Отпуск без содержания',
            'maternity': 'Декретный отпуск',
            'educational': 'Учебный отпуск',
        }

        messages = []
        email_items = []
        for vac in vacations:
            emp = vac.employee
            days_until = (vac.start_date - today).days
            vac_type_name = vac_type_map.get(vac.vacation_type, 'Отпуск')

            if days_until == 0:
                text = (
                    f"🏖️ <b>Сегодня начинается отпуск</b>\n"
                    f"Сотрудник: {emp.full_name}\n"
                    f"Тип: {vac_type_name}\n"
                    f"Период: {vac.start_date.strftime('%d.%m.%Y')} — {vac.end_date.strftime('%d.%m.%Y')}"
                )
                title = 'Сегодня начинается отпуск'
            else:
                text = (
                    f"🏖️ <b>Завтра начинается отпуск</b>\n"
                    f"Сотрудник: {emp.full_name}\n"
                    f"Тип: {vac_type_name}\n"
                    f"Период: {vac.start_date.strftime('%d.%m.%Y')} — {vac.end_date.strftime('%d.%m.%Y')}"
                )
                title = 'Завтра начинается отпуск'

            messages.append(text)
            email_items.append((emp, vac, title))

        if not messages:
            continue

        # Telegram
        try:
            _send_telegram('\n\n'.join(messages))
        except Exception as e:
            logger.error(f'Vacation Telegram error company {company.id}: {e}')

        # Email (если тариф позволяет)
        if _has_email_notify(company):
            for emp, vac, title in email_items:
                try:
                    _send_hr_email(
                        company=company,
                        icon='🏖️',
                        title=title,
                        employee_name=emp.full_name,
                        position=emp.position or '',
                        event_date=vac.start_date.strftime('%d.%m.%Y'),
                        description=f'{vac.get_vacation_type_display()} до {vac.end_date.strftime("%d.%m.%Y")}',
                    )
                except Exception as e:
                    logger.error(f'Vacation email error: {e}')

        notified += len(messages)

    return f"Vacation event check for {today}: notified {notified}"


@shared_task(name="events.check_vacation_endings")
def check_vacation_endings():
    """Напоминание за 3 дня до окончания отпуска сотрудника."""
    from apps.vacations.models import Vacation
    from apps.companies.models import Company

    today = timezone.now().date()
    target = today + timedelta(days=3)
    notified = 0

    for company in Company.objects.select_related('owner').all():
        vacations = Vacation.objects.filter(
            employee__company=company,
            employee__status='active',
            end_date=target,
        ).select_related('employee')

        if not vacations.exists():
            continue

        vac_type_map = {
            'annual': 'Ежегодный отпуск',
            'additional': 'Доп. отпуск',
            'unpaid': 'Отпуск без содержания',
            'maternity': 'Декретный отпуск',
            'educational': 'Учебный отпуск',
        }

        messages = []
        email_items = []
        for vac in vacations:
            emp = vac.employee
            vac_type_name = vac_type_map.get(vac.vacation_type, 'Отпуск')
            text = (
                f"🏖️ <b>Отпуск заканчивается через 3 дня</b>\n"
                f"Сотрудник: {emp.full_name}\n"
                f"Должность: {emp.position}\n"
                f"Тип: {vac_type_name}\n"
                f"Компания: {company.name}\n"
                f"Дата выхода: {vac.end_date.strftime('%d.%m.%Y')}"
            )
            messages.append(text)
            email_items.append((emp, vac, vac_type_name))

        if not messages:
            continue

        # Telegram
        try:
            _send_telegram('\n\n'.join(messages))
        except Exception as e:
            logger.error(f'Vacation ending Telegram error company {company.id}: {e}')

        # Email руководителю
        if _has_email_notify(company):
            for emp, vac, vac_type_name in email_items:
                try:
                    _send_hr_email(
                        company=company,
                        icon='🏖️',
                        title='Сотрудник выходит из отпуска через 3 дня',
                        employee_name=emp.full_name,
                        position=emp.position or '',
                        event_date=vac.end_date.strftime('%d.%m.%Y'),
                        description=f'{vac_type_name} завершается {vac.end_date.strftime("%d.%m.%Y")}. Подготовьте рабочее место.',
                    )
                except Exception as e:
                    logger.error(f'Vacation ending email error: {e}')

        notified += len(messages)

    return f"Vacation ending check for {today}: notified {notified}"
