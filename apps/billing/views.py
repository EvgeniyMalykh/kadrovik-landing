import json
from django.shortcuts import redirect, render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from apps.companies.models import CompanyMember
from apps.billing.models import Payment, Subscription
import logging
logger = logging.getLogger(__name__)
from apps.billing.services import create_payment, activate_subscription, PLANS
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings as django_settings

# ===== ROLE-BASED ACCESS CONTROL =====
ROLE_RANK = {
    'owner': 4,
    'admin': 3,
    'hr': 2,
    'accountant': 1,
}

def _check_role(request, min_role):
    """Проверяет роль. Возвращает True если доступ разрешён."""
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return False
    return ROLE_RANK.get(member.role, 0) >= ROLE_RANK.get(min_role, 99)


@login_required
def checkout(request, plan_key):
    import sys; print(f"[CHK] user={request.user} plan={plan_key}", file=sys.stderr, flush=True)
    """Инициирует оплату через ЮKassa с save_payment_method для рекуррента."""
    if plan_key not in PLANS:
        return redirect("dashboard:subscription")

    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:subscription")

    role_ok = _check_role(request, "owner"); import sys; print(f"[CHK] role_ok={role_ok} user={request.user.email}", file=sys.stderr, flush=True)
    if not role_ok:
        messages.error(request, 'Управление подпиской доступно только владельцу.')
        return redirect("dashboard:subscription")

    return_url = request.build_absolute_uri("/dashboard/payment/success/")

    try:
        payment, confirmation_url = create_payment(member.company, plan_key, return_url)
    except Exception as e:
        import traceback, logging
        logger = logging.getLogger("billing")
        logger.error(f"checkout error plan={plan_key}: {e}\n{traceback.format_exc()}")
        messages.error(request, f"Ошибка оплаты: {e}")
        return redirect("dashboard:subscription")

    if confirmation_url:
        return redirect(confirmation_url)
    else:
        # Заглушка — если ключи не настроены
        activate_subscription(member.company, plan_key)
        payment.status = Payment.Status.SUCCESS
        payment.save(update_fields=["status"])
        return redirect("billing:payment_success")


@login_required
def payment_success(request):
    """Страница после возврата с ЮKassa — статус уточняем по webhook."""
    return redirect("dashboard:subscription")


@login_required
@require_POST
def cancel_autorenew(request):
    """Отключает автопродление и отвязывает карту (очищает payment_method_id)."""
    role_ok = _check_role(request, "owner"); import sys; print(f"[CHK] role_ok={role_ok} user={request.user.email}", file=sys.stderr, flush=True)
    if not role_ok:
        messages.error(request, 'Управление подпиской доступно только владельцу.')
        return redirect("dashboard:subscription")
    member = CompanyMember.objects.filter(user=request.user).first()
    if member:
        sub = getattr(member.company, 'subscription', None)
        if sub:
            sub.auto_renew = False
            sub.payment_method_id = ''
            sub.save(update_fields=['auto_renew', 'payment_method_id'])
            messages.success(request, 'Карта отвязана. Автопродление отключено.')
    return redirect("dashboard:subscription")


@login_required
@require_POST
def detach_card(request):
    """Отвязывает карту — удаляет payment_method_id из системы (требование ЮКассы)."""
    role_ok = _check_role(request, "owner"); import sys; print(f"[CHK] role_ok={role_ok} user={request.user.email}", file=sys.stderr, flush=True)
    if not role_ok:
        messages.error(request, 'Управление подпиской доступно только владельцу.')
        return redirect("dashboard:subscription")
    member = CompanyMember.objects.filter(user=request.user).first()
    if not member:
        return redirect("dashboard:login")
    sub = Subscription.objects.filter(company=member.company).order_by('-started_at').first()
    if sub:
        sub.payment_method_id = ''
        sub.auto_renew = False
        sub.save(update_fields=['payment_method_id', 'auto_renew'])
        messages.success(request, 'Карта отвязана. Автопродление отключено.')
    return redirect("dashboard:subscription")


@csrf_exempt
@require_POST
def yukassa_webhook(request):
    """
    Webhook от ЮKassa.
    Обрабатывает события:
      - payment.succeeded  — активирует подписку
      - payment.canceled   — помечает платёж как failed
    При первом платеже сохраняет payment_method_id для рекуррента.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event = data.get("event", "")
    obj = data.get("object", {})

    # ── payment.succeeded ─────────────────────────────────────────────────────
    if event == "payment.succeeded":
        yukassa_id    = obj.get("id", "")
        metadata      = obj.get("metadata", {})
        payment_db_id = metadata.get("payment_db_id")
        plan_key      = metadata.get("plan")

        if not payment_db_id or not plan_key:
            return HttpResponse(status=400)

        try:
            payment = Payment.objects.get(id=payment_db_id)
        except Payment.DoesNotExist:
            return HttpResponse(status=404)

        payment.status = Payment.Status.SUCCESS
        payment.yukassa_payment_id = yukassa_id
        payment.save(update_fields=["status", "yukassa_payment_id"])

        # Сохраняем payment_method_id если он есть (первый платёж с save_payment_method)
        payment_method = obj.get("payment_method", {})
        saved = payment_method.get("saved", False)
        method_id = payment_method.get("id", "") if saved else ""

        sub = activate_subscription(payment.company, plan_key, payment_method_id=method_id or None)

        # Отправляем email об успешной оплате
        try:
            PLAN_NAMES = {
                'start': 'Старт', 'business': 'Бизнес',
                'pro': 'Корпоратив', 'trial': 'Пробный'
            }
            # Получаем email владельца компании
            from apps.companies.models import CompanyMember
            owner = CompanyMember.objects.filter(
                company=payment.company, role='owner'
            ).select_related('user').first()
            if owner:
                expires_str = sub.expires_at.strftime('%d.%m.%Y') if sub.expires_at else '—'
                html = render_to_string('emails/subscription_activated.html', {
                    'plan_name':     PLAN_NAMES.get(plan_key, plan_key),
                    'company_name':  payment.company.name,
                    'expires_at':    expires_str,
                    'max_employees': sub.max_employees,
                    'amount':        int(payment.amount),
                })
                plain = (
                    f'Оплата прошла успешно!\n\n'
                    f'Тариф {PLAN_NAMES.get(plan_key, plan_key)} активирован для {payment.company.name}.\n'
                    f'Действует до: {expires_str}\n\n'
                    f'Кадровый автопилот — app.kadrovik-auto.ru'
                )
                send_mail(
                    subject='✅ Оплата прошла — тариф активирован',
                    message=plain,
                    from_email=django_settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[owner.user.email],
                    html_message=html,
                    fail_silently=True,
                )
                logger.info(f"[billing] Email об оплате отправлен на {owner.user.email}")
        except Exception as e:
            logger.warning(f"[billing] Не удалось отправить email об оплате: {e}")

    # ── payment.canceled ──────────────────────────────────────────────────────
    elif event == "payment.canceled":
        yukassa_id    = obj.get("id", "")
        metadata      = obj.get("metadata", {})
        payment_db_id = metadata.get("payment_db_id")

        if payment_db_id:
            try:
                payment = Payment.objects.get(id=payment_db_id)
                payment.status = Payment.Status.FAILED
                payment.yukassa_payment_id = yukassa_id
                payment.save(update_fields=["status", "yukassa_payment_id"])
            except Payment.DoesNotExist:
                pass

    return HttpResponse(status=200)
