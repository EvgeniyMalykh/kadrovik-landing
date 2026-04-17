from rest_framework.permissions import BasePermission
from apps.billing.models import Subscription
from apps.billing.services import PLANS
from apps.companies.models import CompanyMember


def get_company_plan_features(user):
    """Возвращает dict фич тарифа компании пользователя."""
    member = CompanyMember.objects.filter(user=user).first()
    if not member:
        return {}
    sub = getattr(member.company, 'subscription', None)
    plan = sub.plan if sub else 'trial'
    return PLANS.get(plan, PLANS['trial'])['features']


class HasAPIAccess(BasePermission):
    """Разрешает доступ только пользователям с тарифом pro (api: True)."""
    message = 'API доступен только на тарифе Корпоратив (pro).'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        features = get_company_plan_features(request.user)
        return features.get('api', False)
