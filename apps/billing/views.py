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
from apps.billing.services import create_payment, activate_subscription, detach_payment_method, PLANS
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

def _get_active_member(request):
    """Возвращает активный CompanyMember с учётом active_company_id из сессии."""
    active_id = request.session.get('active_company_id')
    if active_id:
        member = CompanyMember.objects.filter(user=request.user, company_id=active_id).first()
        if member:
            return member
    return CompanyMember.objects.filter(user=request.user).order_by('-pk').first()

def _check_role(request, min_role):
    """Проверяет роль. Возвращает True если доступ разрешён."""
    member = _get_active_member(request)
    if not member:
        return False
    return ROLE_RANK.get(member.role, 0) >= ROLE_RANK.get(min_role, 99)


@login_required
def checkout(request, plan_key):
    """Инициирует оплату через ЮKassa с save_payment_method для рекуррента."""
    if plan_key not in PLANS:
        return redirect("dashboard:subscription")

    member = _get_active_member(request)
    if not member:
        return redirect("dashboard:subscription")

    role_ok = _check_role(request, "owner")
    if not role_ok:
        messages.error(request, 'Управление подпиской доступно только владельцу.')
        return redirect("dashboard:subscription")

    billing_period = request.GET.get('period', 'monthly')
    if billing_period not in ('monthly', 'annual'):
        billing_period = 'monthly'

    # Защита от дублей: если есть pending-платёж младше 10 минут — перенаправляем на него
    from django.utils import timezone
    from datetime import timedelta
    recent_pending = Payment.objects.filter(
        company=member.company,
        status=Payment.Status.PENDING,
        created_at__gte=timezone.now() - timedelta(minutes=10),
    ).exclude(yukassa_payment_id='').order_by('-created_at').first()
    if recent_pending and recent_pending.yukassa_payment_id:
        try:
            from apps.billing.services import _get_yookassa
            yookassa = _get_yookassa()
            yk = yookassa.Payment.find_one(recent_pending.yukassa_payment_id)
            if yk.status == 'pending' and yk.confirmation:
                confirmation_url = yk.confirmation.confirmation_url
                if confirmation_url:
                    return redirect(confirmation_url)
        except Exception:
            pass

    return_url = request.build_absolute_uri("/dashboard/payment/success/")

    try:
        payment, confirmation_url = create_payment(member.company, plan_key, return_url, billing_period=billing_period)
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
        activate_subscription(member.company, plan_key, billing_period=billing_period)
        payment.status = Payment.Status.SUCCESS
        payment.save(update_fields=["status"])
        return redirect("billing:payment_success")


@login_required
def payment_success(request):
    """Страница после возврата с ЮKassa.

    Проверяем последний pending-платёж компании через API ЮKassa,
    чтобы обновить статус, не дожидаясь webhook (race condition).
    """
    member = _get_active_member(request)
    if member:
        _sync_pending_payments(member.company)
    return redirect("dashboard:subscription")


def _sync_pending_payments(company):
    """Проверяет pending-платежи через API ЮKassa и обновляет статусы."""
    from apps.billing.services import _get_yookassa, activate_subscription
    pending = Payment.objects.filter(
        company=company,
        status=Payment.Status.PENDING,
    ).exclude(yukassa_payment_id='').order_by('-created_at')[:5]

    if not pending:
        return

    try:
        yookassa = _get_yookassa()
    except Exception:
        return

    for payment in pending:
        try:
            yk = yookassa.Payment.find_one(payment.yukassa_payment_id)
        except Exception as e:
            logger.warning(f"[sync] YK API error for {payment.yukassa_payment_id}: {e}")
            continue

        if yk.status == 'succeeded' and payment.status != Payment.Status.SUCCESS:
            payment.status = Payment.Status.SUCCESS
            payment.save(update_fields=["status"])
            metadata = yk.metadata or {}
            plan_key = metadata.get("plan", payment.plan)
            billing_period = metadata.get("billing_period", "monthly")
            pm = yk.payment_method
            method_id = pm.id if pm and getattr(pm, 'saved', False) else None
            sub = activate_subscription(company, plan_key, payment_method_id=method_id, billing_period=billing_period)
            # Сохраняем данные карты
            if pm and hasattr(pm, 'card') and pm.card:
                card_last4 = getattr(pm.card, 'last4', '')
                card_brand = getattr(pm.card, 'card_type', '')
                if card_last4:
                    sub.card_last4 = card_last4
                    sub.card_brand = card_brand
                    sub.save(update_fields=["card_last4", "card_brand"])
            logger.info(f"[sync] Payment {payment.id} synced as succeeded")
        elif yk.status == 'canceled' and payment.status != Payment.Status.FAILED:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status"])
            logger.info(f"[sync] Payment {payment.id} synced as canceled")


@login_required
@require_POST
def cancel_autorenew(request):
    """Отключает автопродление и отвязывает карту через ЮКасса API."""
    role_ok = _check_role(request, "owner")
    if not role_ok:
        messages.error(request, 'Управление подпиской доступно только владельцу.')
        return redirect("dashboard:subscription")
    member = _get_active_member(request)
    if member:
        sub = getattr(member.company, 'subscription', None)
        if sub and sub.payment_method_id:
            success, error = detach_payment_method(sub)
            if success:
                messages.success(request, 'Карта отвязана. Автопродление отключено.')
            else:
                messages.error(request, f'Не удалось отвязать карту: {error}')
        elif sub:
            sub.auto_renew = False
            sub.save(update_fields=['auto_renew'])
            messages.success(request, 'Автопродление отключено.')
    return redirect("dashboard:subscription")


@login_required
@require_POST
def detach_card(request):
    """Отвязывает карту через ЮКасса API (DELETE payment_method)."""
    role_ok = _check_role(request, "owner")
    if not role_ok:
        messages.error(request, 'Управление подпиской доступно только владельцу.')
        return redirect("dashboard:subscription")
    member = _get_active_member(request)
    if not member:
        return redirect("dashboard:login")
    sub = Subscription.objects.filter(company=member.company).order_by('-started_at').first()
    if not sub:
        messages.error(request, 'Подписка не найдена.')
        return redirect("dashboard:subscription")
    if not sub.payment_method_id:
        messages.info(request, 'Карта уже отвязана.')
        return redirect("dashboard:subscription")
    success, error = detach_payment_method(sub)
    if success:
        messages.success(request, 'Карта успешно отвязана. Автопродление отключено.')
    else:
        messages.error(request, f'Не удалось отвязать карту: {error}')
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
        logger.warning("[webhook] Invalid JSON body")
        return HttpResponse(status=400)

    event = data.get("event", "")
    obj = data.get("object", {})
    logger.info(f"[webhook] event={event} yukassa_id={obj.get('id', '?')}")

    # ── payment.succeeded ─────────────────────────────────────────────────────
    if event == "payment.succeeded":
        yukassa_id    = obj.get("id", "")
        metadata      = obj.get("metadata", {})
        payment_db_id = metadata.get("payment_db_id")
        plan_key      = metadata.get("plan")

        if not payment_db_id or not plan_key:
            logger.warning(f"[webhook] payment.succeeded missing metadata: {metadata}")
            return HttpResponse(status=400)

        try:
            payment = Payment.objects.get(id=payment_db_id)
        except Payment.DoesNotExist:
            logger.warning(f"[webhook] payment.succeeded DB id={payment_db_id} not found")
            return HttpResponse(status=404)

        payment.status = Payment.Status.SUCCESS
        payment.yukassa_payment_id = yukassa_id
        payment.save(update_fields=["status", "yukassa_payment_id"])

        # Сохраняем payment_method_id если он есть (первый платёж с save_payment_method)
        payment_method = obj.get("payment_method", {})
        saved = payment_method.get("saved", False)
        method_id = payment_method.get("id", "") if saved else ""

        billing_period = metadata.get("billing_period", "monthly")
        sub = activate_subscription(payment.company, plan_key, payment_method_id=method_id or None, billing_period=billing_period)

        # Сохраняем данные карты из ответа ЮКасса
        card_data = payment_method.get("card", {})
        card_last4 = card_data.get("last4", "")
        card_brand = card_data.get("card_type", "")
        if card_last4:
            sub.card_last4 = card_last4
            sub.card_brand = card_brand
            sub.save(update_fields=["card_last4", "card_brand"])

        logger.info(f"[webhook] Subscription activated: company={payment.company_id} plan={plan_key} period={billing_period} expires={sub.expires_at}")

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
        cancel_details = obj.get("cancellation_details", {})
        logger.info(f"[webhook] payment.canceled db_id={payment_db_id} reason={cancel_details.get('reason', '?')} party={cancel_details.get('party', '?')}")

        if payment_db_id:
            try:
                payment = Payment.objects.get(id=payment_db_id)
                payment.status = Payment.Status.FAILED
                payment.yukassa_payment_id = yukassa_id
                payment.save(update_fields=["status", "yukassa_payment_id"])
            except Payment.DoesNotExist:
                logger.warning(f"[webhook] payment.canceled DB id={payment_db_id} not found")

    return HttpResponse(status=200)


def donate(request):
    """Создаёт разовый платёж в ЮКасса на произвольную сумму (поддержка проекта).
    POST: amount — сумма в рублях (целое число, минимум 10).
    Возвращает редирект на страницу оплаты ЮКасса.
    """
    from django.conf import settings
    from django.shortcuts import redirect
    try:
        # Поддерживаем и POST (дашборд) и GET (лендинг)
        raw = request.POST.get('amount') or request.GET.get('amount', '0')
        amount = int(raw)
    except (ValueError, TypeError):
        amount = 0

    if amount < 10:
        from django.contrib import messages
        messages.error(request, 'Минимальная сумма перевода — 10 ₽')
        return redirect(request.META.get('HTTP_REFERER', '/'))

    import uuid
    from apps.billing.services import _get_yookassa

    shop_id = getattr(settings, 'YUKASSA_SHOP_ID', '')
    secret_key = getattr(settings, 'YUKASSA_SECRET_KEY', '')
    if not shop_id or not secret_key:
        from django.http import HttpResponseServerError
        return HttpResponseServerError('Платёжный модуль не настроен')

    return_url = request.build_absolute_uri('/dashboard/')
    idempotence_key = str(uuid.uuid4())

    try:
        yookassa = _get_yookassa()
        yk_payment = yookassa.Payment.create({
            'amount': {
                'value': str(amount) + '.00',
                'currency': 'RUB',
            },
            'confirmation': {
                'type': 'redirect',
                'return_url': return_url,
            },
            'capture': True,
            'description': 'Поддержка проекта «Кадровый автопилот»',
            'metadata': {'type': 'donation'},
        }, idempotence_key)
        confirmation_url = yk_payment.confirmation.confirmation_url
        from django.shortcuts import redirect
        return redirect(confirmation_url)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Donate payment error: {e}')
        from django.shortcuts import redirect
        from django.contrib import messages
        messages.error(request, f'Ошибка создания платежа: {e}')
        return redirect(request.META.get('HTTP_REFERER', '/'))
