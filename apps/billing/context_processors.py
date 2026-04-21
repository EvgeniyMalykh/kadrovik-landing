"""
Context processor — добавляет информацию о тарифе в каждый шаблон.
"""
import math
from django.utils import timezone
from apps.billing.services import get_subscription_context, FEATURE_PLAN_LABEL


def subscription_features(request):
    """Добавляет plan_features, plan_key, can_add_employee во все шаблоны."""
    if not request.user.is_authenticated:
        return {
            "plan_features": {},
            "plan_key": "start",
            "can_add_employee": False,
            "max_employees": 10,
            "employee_count": 0,
            "feature_plan_label": FEATURE_PLAN_LABEL,
        }
    try:
        from apps.companies.models import CompanyMember
        active_id = request.session.get('active_company_id')
        if active_id:
            member = CompanyMember.objects.filter(user=request.user, company_id=active_id).first()
        else:
            member = None
        if not member:
            member = CompanyMember.objects.filter(user=request.user).order_by('-pk').first()
        company = member.company if member else None
        ctx = get_subscription_context(company)
        ctx['subscription'] = ctx.get('sub')
        ctx['member'] = member
        ctx['member_role'] = member.role if member else None

        # Добавляем информацию о grace period
        sub = ctx.get('sub')
        if sub and sub.data_deletion_scheduled_at:
            now = timezone.now()
            delta = sub.data_deletion_scheduled_at - now
            ctx['data_deletion_date'] = sub.data_deletion_scheduled_at
            ctx['days_until_deletion'] = max(0, math.ceil(delta.total_seconds() / 86400))
        else:
            ctx['data_deletion_date'] = None
            ctx['days_until_deletion'] = None
        ctx['data_cleaned'] = sub.data_cleaned if sub else False

        return ctx
    except Exception:
        return {
            "plan_features": {},
            "plan_key": "start",
            "can_add_employee": False,
            "max_employees": 10,
            "employee_count": 0,
            "feature_plan_label": FEATURE_PLAN_LABEL,
        }
