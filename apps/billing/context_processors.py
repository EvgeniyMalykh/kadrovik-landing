"""
Context processor — добавляет информацию о тарифе в каждый шаблон.
"""
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
        member = CompanyMember.objects.filter(user=request.user).first()
        company = member.company if member else None
        ctx = get_subscription_context(company)
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
