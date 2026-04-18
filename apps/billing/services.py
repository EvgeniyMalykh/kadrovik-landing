import uuid
import logging
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from apps.billing.models import Payment, Subscription

logger = logging.getLogger(__name__)

# Лимиты и фичи по тарифам
PLANS = {
    "trial": {
        "name": "Пробный",
        "price": 0,
        "max_employees": 50,
        "months": 0,
        "features": {
            "documents":         True,
            "telegram":          True,
            "timesheet":         True,
            "email_notify":      True,
            "multi_user":        True,
            "export_excel":      False,
            "custom_templates":  False,
            "priority_support":  False,
            "api":               False,
            "sfr_export":        False,
        },
    },
    "start": {
        "name": "Старт",
        "price": 790,
        "max_employees": 10,
        "months": 1,
        "features": {
            "documents":         True,
            "telegram":          True,
            "timesheet":         True,
            "email_notify":      False,
            "multi_user":        False,
            "export_excel":      False,
            "custom_templates":  False,
            "priority_support":  False,
            "api":               False,
            "sfr_export":        False,
        },
    },
    "business": {
        "name": "Бизнес",
        "price": 1990,
        "max_employees": 50,
        "months": 1,
        "features": {
            "documents":         True,
            "telegram":          True,
            "timesheet":         True,
            "email_notify":      True,
            "multi_user":        True,
            "export_excel":      True,
            "custom_templates":  False,
            "priority_support":  False,
            "api":               False,
            "sfr_export":        False,
        },
    },
    "pro": {
        "name": "Корпоратив",
        "price": 4900,
        "max_employees": 200,
        "months": 1,
        "features": {
            "documents":         True,
            "telegram":          True,
            "timesheet":         True,
            "email_notify":      True,
            "multi_user":        True,
            "export_excel":      True,
            "custom_templates":  True,
            "priority_support":  True,
            "api":               True,
            "sfr_export":        True,
        },
    },
}

FEATURE_PLAN_LABEL = {
    "email_notify":     "Бизнес",
    "multi_user":       "Бизнес",
    "export_excel":     "Бизнес",
    "custom_templates": "Корпоратив",
    "priority_support": "Корпоратив",
    "api":              "Корпоратив",
    "sfr_export":       "Корпоратив",
}


def get_plan_features(plan_key):
    plan = PLANS.get(plan_key, PLANS["start"])
    return plan["features"]


def get_subscription_context(company):
    from apps.employees.models import Employee
    sub = getattr(company, "subscription", None) if company else None
    plan_key = sub.plan if sub else "start"
    features = get_plan_features(plan_key)
    plan_data = PLANS.get(plan_key, PLANS["start"])
    max_emp = plan_data["max_employees"]
    emp_count = Employee.objects.filter(company=company).count() if company else 0
    return {
        "sub": sub,
        "plan_key": plan_key,
        "plan_features": features,
        "max_employees": max_emp,
        "employee_count": emp_count,
        "can_add_employee": emp_count < max_emp,
        "feature_plan_label": FEATURE_PLAN_LABEL,
    }


def _get_yookassa():
    """Настраивает и возвращает модуль yookassa."""
    import yookassa
    yookassa.Configuration.account_id = getattr(settings, 'YUKASSA_SHOP_ID', '')
    yookassa.Configuration.secret_key = getattr(settings, 'YUKASSA_SECRET_KEY', '')
    return yookassa


def create_payment(company, plan_key, return_url):
    """
    Создаёт платёж через ЮKassa.
    Пытается создать с save_payment_method=True для рекуррентных платежей.
    Если ЮKassa отклоняет (автоплатежи не включены в кабинете), создаёт обычный платёж.
    Возвращает (payment_db, confirmation_url).
    """
    plan = PLANS[plan_key]

    payment = Payment.objects.create(
        company=company,
        amount=plan["price"],
        plan=plan_key,
        status=Payment.Status.PENDING,
    )

    shop_id = getattr(settings, 'YUKASSA_SHOP_ID', '')
    secret_key = getattr(settings, 'YUKASSA_SECRET_KEY', '')

    if not shop_id or not secret_key:
        return payment, None

    try:
        yookassa = _get_yookassa()
        idempotence_key = str(uuid.uuid4())

        owner_email = "noreply@kadrovik-auto.ru"
        owner_member = company.members.filter(role='owner').first()
        if owner_member:
            owner_email = owner_member.user.email or owner_email

        payment_data = {
            "amount": {
                "value": f"{plan['price']:.2f}",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url,
            },
            "capture": True,
            "description": f"Подписка «{plan['name']}» — {company.name}",
            "metadata": {
                "payment_db_id": str(payment.id),
                "plan": plan_key,
                "company_id": str(company.id),
            },
            "receipt": {
                "customer": {
                    "email": owner_email,
                },
                "items": [{
                    "description": f"Подписка «{plan['name']}» на 1 месяц",
                    "quantity": "1.00",
                    "amount": {
                        "value": f"{plan['price']:.2f}",
                        "currency": "RUB",
                    },
                    "vat_code": 1,
                    "payment_mode": "full_payment",
                    "payment_subject": "service",
                }],
            },
        }

        # Пытаемся с save_payment_method для автопродления
        payment_data_with_save = {
            **payment_data,
            "payment_method_data": {"type": "bank_card"},
            "save_payment_method": True,
        }

        try:
            yk_payment = yookassa.Payment.create(payment_data_with_save, idempotence_key)
            logger.info(f"[billing] Платёж создан с save_payment_method: {yk_payment.id}")
        except Exception as save_err:
            # ForbiddenError = автоплатежи не включены в кабинете ЮKassa
            # Создаём обычный платёж без сохранения метода
            logger.warning(
                f"[billing] save_payment_method отклонён ({type(save_err).__name__}): {save_err}. "
                f"Создаём обычный платёж."
            )
            idempotence_key = str(uuid.uuid4())
            yk_payment = yookassa.Payment.create(payment_data, idempotence_key)
            logger.info(f"[billing] Платёж создан без save_payment_method: {yk_payment.id}")

        payment.yukassa_payment_id = yk_payment.id
        payment.save(update_fields=["yukassa_payment_id"])

        confirmation_url = yk_payment.confirmation.confirmation_url
        return payment, confirmation_url

    except Exception as e:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status"])
        raise


def create_recurring_payment(company, plan_key):
    """
    Автосписание с сохранённого метода оплаты (рекуррент).
    Вызывается Celery-задачей при продлении подписки.
    """
    sub = getattr(company, 'subscription', None)
    if not sub or not sub.payment_method_id:
        return None

    plan = PLANS.get(plan_key, PLANS['start'])

    payment = Payment.objects.create(
        company=company,
        amount=plan["price"],
        plan=plan_key,
        status=Payment.Status.PENDING,
    )

    try:
        yookassa = _get_yookassa()
        idempotence_key = str(uuid.uuid4())

        yk_payment = yookassa.Payment.create({
            "amount": {
                "value": f"{plan['price']:.2f}",
                "currency": "RUB",
            },
            "capture": True,
            "payment_method_id": sub.payment_method_id,
            "description": f"Автопродление подписки «{plan['name']}» — {company.name}",
            "metadata": {
                "payment_db_id": str(payment.id),
                "plan": plan_key,
                "company_id": str(company.id),
                "recurring": "true",
            },
        }, idempotence_key)

        payment.yukassa_payment_id = yk_payment.id
        payment.save(update_fields=["yukassa_payment_id"])

        # Если сразу succeeded
        if yk_payment.status == 'succeeded':
            payment.status = Payment.Status.SUCCESS
            payment.save(update_fields=["status"])
            activate_subscription(company, plan_key)

        return payment

    except Exception as e:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status"])
        raise


def activate_subscription(company, plan_key, payment_method_id=None):
    """Активирует / продлевает подписку после успешной оплаты."""
    plan = PLANS[plan_key]
    sub, _ = Subscription.objects.get_or_create(company=company)
    sub.plan = plan_key
    sub.status = Subscription.Status.ACTIVE
    sub.started_at = timezone.now()
    sub.max_employees = plan["max_employees"]
    sub.expires_at = timezone.now() + timedelta(days=30 * plan["months"])
    if payment_method_id:
        sub.payment_method_id = payment_method_id
        sub.auto_renew = True
    sub.save()
    return sub
