"""
Celery-задачи для биллинга:
- Автопродление подписок через ЮКассу
- Проверка истекших подписок
- Очистка данных компаний после grace period (30 дней)
- Предупреждения об удалении данных
"""
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

PAID_PLANS = ['start', 'business', 'pro']


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


@shared_task(name="billing.check_expired_subscriptions")
def check_expired_subscriptions():
    """
    Ежедневно проверяет подписки с истекшим сроком и переводит в status=expired.
    Для paid-планов устанавливает data_deletion_scheduled_at (через 30 дней).
    Для trial — просто expired без grace period.
    """
    from apps.billing.models import Subscription

    now = timezone.now()
    expired_subs = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        expires_at__lt=now,
    ).select_related('company')

    count = 0
    for sub in expired_subs:
        sub.status = Subscription.Status.EXPIRED
        if sub.plan in PAID_PLANS:
            sub.data_deletion_scheduled_at = sub.expires_at + timedelta(days=30)
            logger.info(
                f"[billing] Подписка expired (paid): company={sub.company_id} "
                f"plan={sub.plan}, удаление данных: {sub.data_deletion_scheduled_at}"
            )
        else:
            sub.data_deletion_scheduled_at = None
            logger.info(
                f"[billing] Подписка expired (trial): company={sub.company_id}"
            )
        sub.save(update_fields=['status', 'data_deletion_scheduled_at'])
        count += 1

    logger.info(f"[billing] check_expired_subscriptions: переведено в expired: {count}")
    return f"Переведено в expired: {count}"


@shared_task(name="billing.cleanup_expired_company_data")
def cleanup_expired_company_data():
    """
    Ежедневно проверяет компании у которых grace period истёк
    (data_deletion_scheduled_at < now и status=expired).
    Удаляет связанные данные (сотрудники, документы, отпуска и т.д.),
    но НЕ удаляет саму Company и User.
    """
    from apps.billing.models import Subscription
    from apps.employees.models import Employee, Department, TimeRecord, SalaryHistory
    from apps.documents.models import Document, DocumentTemplate
    from apps.vacations.models import Vacation, VacationSchedule, VacationScheduleEntry
    from apps.events.models import HREvent

    now = timezone.now()
    subs = Subscription.objects.filter(
        status=Subscription.Status.EXPIRED,
        data_deletion_scheduled_at__lt=now,
        data_cleaned=False,
    ).exclude(
        data_deletion_scheduled_at__isnull=True,
    ).select_related('company')

    count = 0
    for sub in subs:
        company = sub.company
        logger.info(f"[billing] Начало очистки данных: company={company.id} ({company.name})")

        # Удаляем данные в правильном порядке (зависимости)
        deleted = {}

        # Записи табеля
        d = TimeRecord.objects.filter(employee__company=company).delete()
        deleted['time_records'] = d[0]

        # История окладов
        d = SalaryHistory.objects.filter(employee__company=company).delete()
        deleted['salary_history'] = d[0]

        # HR-события
        d = HREvent.objects.filter(company=company).delete()
        deleted['events'] = d[0]

        # Записи графика отпусков
        d = VacationScheduleEntry.objects.filter(schedule__company=company).delete()
        deleted['vacation_schedule_entries'] = d[0]

        # Графики отпусков
        d = VacationSchedule.objects.filter(company=company).delete()
        deleted['vacation_schedules'] = d[0]

        # Отпуска
        d = Vacation.objects.filter(employee__company=company).delete()
        deleted['vacations'] = d[0]

        # Документы
        d = Document.objects.filter(company=company).delete()
        deleted['documents'] = d[0]

        # Шаблоны документов
        d = DocumentTemplate.objects.filter(company=company).delete()
        deleted['document_templates'] = d[0]

        # Сотрудники
        d = Employee.objects.filter(company=company).delete()
        deleted['employees'] = d[0]

        # Отделы
        d = Department.objects.filter(company=company).delete()
        deleted['departments'] = d[0]

        # Помечаем что данные очищены
        sub.data_cleaned = True
        sub.data_deletion_scheduled_at = None
        sub.save(update_fields=['data_cleaned', 'data_deletion_scheduled_at'])

        logger.info(f"[billing] Данные очищены: company={company.id} ({company.name}), удалено: {deleted}")
        count += 1

    logger.info(f"[billing] cleanup_expired_company_data: очищено компаний: {count}")
    return f"Очищено компаний: {count}"


@shared_task(name="billing.send_expiry_warnings")
def send_expiry_warnings():
    """
    Отправляет email-предупреждения:
    1. Триал: за 3 дня и за 1 день до expires_at (status=active, plan=trial)
    2. Paid: за 7 дней и за 1 день до data_deletion_scheduled_at (status=expired)
    """
    from apps.billing.models import Subscription
    from apps.companies.models import CompanyMember
    from django.core.mail import send_mail
    from django.conf import settings as django_settings

    now = timezone.now()
    sent_count = 0

    def _get_owner_email(company):
        owner_member = CompanyMember.objects.filter(
            company=company, role='owner'
        ).select_related('user').first()
        if not owner_member or not owner_member.user.email:
            logger.warning(f"[billing] Нет email владельца для company={company.id}")
            return None, None
        return owner_member.user.email, owner_member

    def _send(email, subject, plain, html):
        try:
            send_mail(
                subject=subject,
                message=plain,
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html,
                fail_silently=True,
            )
            return True
        except Exception as e:
            logger.error(f"[billing] Ошибка отправки предупреждения: email={email} error={e}")
            return False

    # ── 1. Предупреждения о скором истечении ТРИАЛА ──
    for days_before, label in [(3, '3 дня'), (1, '1 день')]:
        window_start = now + timedelta(days=days_before - 1, hours=12)
        window_end = now + timedelta(days=days_before, hours=12)

        trial_subs = Subscription.objects.filter(
            status=Subscription.Status.ACTIVE,
            plan=Subscription.Plan.TRIAL,
            expires_at__gte=window_start,
            expires_at__lt=window_end,
        ).select_related('company')

        for sub in trial_subs:
            email, _ = _get_owner_email(sub.company)
            if not email:
                continue

            expires_date = sub.expires_at.strftime('%d.%m.%Y')
            company_name = sub.company.name

            subject = f"Пробный период {company_name} истекает через {label}"
            plain = (
                f"Здравствуйте!\n\n"
                f"Пробный период компании «{company_name}» истекает {expires_date}.\n"
                f"После истечения доступ к сервису будет заблокирован.\n\n"
                f"Выберите тариф чтобы продолжить работу:\n"
                f"https://app.kadrovik-auto.ru/dashboard/subscription/\n\n"
                f"С уважением,\n"
                f"Кадровый автопилот"
            )
            html = (
                f"<div style='font-family:sans-serif;max-width:600px;margin:0 auto;'>"
                f"<h2 style='color:#f59e0b;'>&#9200; Пробный период истекает через {label}</h2>"
                f"<p>Пробный период компании <b>{company_name}</b> истекает <b>{expires_date}</b>.</p>"
                f"<p>После истечения доступ к сервису будет заблокирован.</p>"
                f"<p style='margin:24px 0;'>"
                f"<a href='https://app.kadrovik-auto.ru/dashboard/subscription/' "
                f"style='background:#3b82f6;color:#fff;padding:12px 24px;border-radius:8px;"
                f"text-decoration:none;font-weight:600;'>Выбрать тариф</a></p>"
                f"<p style='color:#6b7280;font-size:14px;'>С уважением,<br>Кадровый автопилот</p>"
                f"</div>"
            )

            if _send(email, subject, plain, html):
                sent_count += 1
                logger.info(
                    f"[billing] Предупреждение триал ({label}) отправлено: "
                    f"company={sub.company_id} email={email}"
                )

    # ── 2. Предупреждения об удалении данных (paid планы) ──
    # Предупреждение за 7 дней
    warn_7_start = now + timedelta(days=6, hours=12)
    warn_7_end = now + timedelta(days=7, hours=12)

    # Предупреждение за 1 день
    warn_1_start = now + timedelta(hours=12)
    warn_1_end = now + timedelta(days=1, hours=12)

    for label, dt_start, dt_end, days_left in [
        ('7 дней', warn_7_start, warn_7_end, 7),
        ('1 день', warn_1_start, warn_1_end, 1),
    ]:
        subs = Subscription.objects.filter(
            status=Subscription.Status.EXPIRED,
            data_deletion_scheduled_at__gte=dt_start,
            data_deletion_scheduled_at__lt=dt_end,
            data_cleaned=False,
        ).select_related('company')

        for sub in subs:
            email, _ = _get_owner_email(sub.company)
            if not email:
                continue

            deletion_date = sub.data_deletion_scheduled_at.strftime('%d.%m.%Y')
            company_name = sub.company.name

            subject = f"Данные компании {company_name} будут удалены через {label}"
            plain = (
                f"Здравствуйте!\n\n"
                f"Подписка компании «{company_name}» истекла.\n"
                f"Данные вашего аккаунта (сотрудники, документы, отпуска) "
                f"будут безвозвратно удалены {deletion_date}.\n\n"
                f"Чтобы сохранить данные, продлите подписку:\n"
                f"https://app.kadrovik-auto.ru/dashboard/subscription/\n\n"
                f"С уважением,\n"
                f"Кадровый автопилот"
            )
            html = (
                f"<div style='font-family:sans-serif;max-width:600px;margin:0 auto;'>"
                f"<h2 style='color:#dc2626;'>&#9888;&#65039; Данные будут удалены через {label}</h2>"
                f"<p>Подписка компании <b>{company_name}</b> истекла.</p>"
                f"<p>Данные вашего аккаунта (сотрудники, документы, отпуска) "
                f"будут <b>безвозвратно удалены {deletion_date}</b>.</p>"
                f"<p style='margin:24px 0;'>"
                f"<a href='https://app.kadrovik-auto.ru/dashboard/subscription/' "
                f"style='background:#3b82f6;color:#fff;padding:12px 24px;border-radius:8px;"
                f"text-decoration:none;font-weight:600;'>Продлить подписку</a></p>"
                f"<p style='color:#6b7280;font-size:14px;'>С уважением,<br>Кадровый автопилот</p>"
                f"</div>"
            )

            if _send(email, subject, plain, html):
                sent_count += 1
                logger.info(
                    f"[billing] Предупреждение ({label}) отправлено: "
                    f"company={sub.company_id} email={email}"
                )

    logger.info(f"[billing] send_expiry_warnings: отправлено {sent_count} писем")
    return f"Отправлено предупреждений: {sent_count}"
