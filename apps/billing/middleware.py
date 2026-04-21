import math
from django.shortcuts import redirect
from django.utils import timezone

PROTECTED_PREFIXES = ['/dashboard/', '/vacations/']

EXEMPT_PATHS = [
    '/dashboard/login/',
    '/dashboard/logout/',
    '/dashboard/register/',
    '/dashboard/verify-email/',
    '/dashboard/forgot-password/',
    '/dashboard/reset-password/',
    '/dashboard/subscription/',
    '/dashboard/checkout/',
    '/dashboard/payment/',
    '/dashboard/webhook/',
    '/dashboard/invite/',
    '/vacations/request/',
    '/billing/',
    '/static/',
    '/media/',
    '/admin/',
]


class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        protected = any(request.path.startswith(p) for p in PROTECTED_PREFIXES)
        if protected and request.user.is_authenticated:
            exempt = any(request.path.startswith(p) for p in EXEMPT_PATHS)
            if not exempt:
                from apps.companies.models import CompanyMember
                active_id = request.session.get('active_company_id')
                if active_id:
                    member = CompanyMember.objects.filter(user=request.user, company_id=active_id).first()
                else:
                    member = None
                if not member:
                    member = CompanyMember.objects.filter(user=request.user).order_by('-pk').first()
                if member:
                    sub = getattr(member.company, 'subscription', None)
                    if sub and not sub.is_active:
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                           request.headers.get('HX-Request'):
                            from django.http import JsonResponse
                            return JsonResponse({'error': 'subscription_expired', 'redirect': '/dashboard/subscription/'}, status=402)
                        return redirect('/dashboard/subscription/')

                    # Добавляем информацию о grace period в request для шаблонов
                    if sub and sub.data_deletion_scheduled_at:
                        now = timezone.now()
                        delta = sub.data_deletion_scheduled_at - now
                        request.data_deletion_date = sub.data_deletion_scheduled_at
                        request.days_until_deletion = max(0, math.ceil(delta.total_seconds() / 86400))
                    else:
                        request.data_deletion_date = None
                        request.days_until_deletion = None

        return self.get_response(request)
