import json
import hashlib
import hmac
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from apps.companies.models import CompanyMember
from apps.billing.models import Payment
from apps.billing.services import create_payment, activate_subscription, PLANS


@login_required
def checkout(request, plan_key):
    """Инициирует оплату. Если ЮKassa не настроена — симулирует успех (демо)."""
    if plan_key not in PLANS:
        return redirect("dashboard:subscription")

    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:subscription")

    return_url = request.build_absolute_uri("/dashboard/payment/success/")

    try:
        payment, confirmation_url = create_payment(member.company, plan_key, return_url)
    except Exception:
        return redirect("dashboard:subscription")

    if confirmation_url:
        # Реальный редирект на страницу оплаты ЮKassa
        return redirect(confirmation_url)
    else:
        # Заглушка — активируем сразу (для тестирования без ключей)
        activate_subscription(member.company, plan_key)
        payment.status = Payment.Status.SUCCESS
        payment.save(update_fields=["status"])
        return redirect("dashboard:payment_success")


@login_required
def payment_success(request):
    """Страница после успешной оплаты."""
    member = CompanyMember.objects.filter(user=request.user).first()
    sub = getattr(member.company, "subscription", None) if member else None
    return redirect("dashboard:subscription")


@csrf_exempt
@require_POST
def yukassa_webhook(request):
    """Webhook от ЮKassa — подтверждает оплату и активирует подписку."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event = data.get("event")
    if event != "payment.succeeded":
        return HttpResponse(status=200)

    payment_data = data.get("object", {})
    yukassa_id   = payment_data.get("id", "")
    metadata     = payment_data.get("metadata", {})
    payment_db_id = metadata.get("payment_db_id")
    plan_key      = metadata.get("plan")

    if not payment_db_id or not plan_key:
        return HttpResponse(status=400)

    try:
        payment = Payment.objects.get(id=payment_db_id)
        payment.status = Payment.Status.SUCCESS
        payment.yukassa_payment_id = yukassa_id
        payment.save(update_fields=["status", "yukassa_payment_id"])
        activate_subscription(payment.company, plan_key)
    except Payment.DoesNotExist:
        return HttpResponse(status=404)

    return HttpResponse(status=200)
