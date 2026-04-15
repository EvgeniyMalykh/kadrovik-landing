import uuid
import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from apps.billing.models import Payment, Subscription


YUKASSA_API_URL = "https://api.yookassa.ru/v3/payments"

PLANS = {
    "start":    {"name": "Старт",      "price": 790,  "max_employees": 10,  "months": 1},
    "business": {"name": "Бизнес",     "price": 1990, "max_employees": 50,  "months": 1},
    "pro":      {"name": "Корпоратив", "price": 4900, "max_employees": 9999,"months": 1},
}


def create_payment(company, plan_key, return_url):
    """
    Создаёт платёж в ЮKassa и возвращает (payment_db, confirmation_url).
    Если YUKASSA_SHOP_ID не задан — возвращает (payment_db, None) для режима заглушки.
    """
    plan = PLANS[plan_key]
    shop_id = getattr(settings, "YUKASSA_SHOP_ID", "")
    secret_key = getattr(settings, "YUKASSA_SECRET_KEY", "")

    # Создаём запись платежа в БД
    payment = Payment.objects.create(
        company=company,
        amount=plan["price"],
        plan=plan_key,
        status=Payment.Status.PENDING,
    )

    if not shop_id or not secret_key:
        # Режим заглушки — ключи не настроены
        return payment, None

    idempotence_key = str(uuid.uuid4())
    payload = {
        "amount": {"value": str(plan["price"]) + ".00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": f"Подписка «{plan['name']}» — {company.name}",
        "metadata": {"payment_db_id": payment.id, "plan": plan_key, "company_id": company.id},
    }

    try:
        resp = requests.post(
            YUKASSA_API_URL,
            json=payload,
            auth=(shop_id, secret_key),
            headers={"Idempotence-Key": idempotence_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        payment.yukassa_payment_id = data["id"]
        payment.save(update_fields=["yukassa_payment_id"])
        confirmation_url = data["confirmation"]["confirmation_url"]
        return payment, confirmation_url
    except Exception as e:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status"])
        raise


def activate_subscription(company, plan_key):
    """Активирует / продлевает подписку после успешной оплаты."""
    plan = PLANS[plan_key]
    sub, _ = Subscription.objects.get_or_create(company=company)
    sub.plan = plan_key
    sub.status = Subscription.Status.ACTIVE
    sub.max_employees = plan["max_employees"]
    sub.expires_at = timezone.now() + timedelta(days=30 * plan["months"])
    sub.save()
    return sub
