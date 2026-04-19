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
    '/dashboard/employees/',
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
            # Проверяем не освобождён ли путь
            exempt = any(request.path.startswith(p) for p in EXEMPT_PATHS)
            if not exempt:
                from apps.companies.models import CompanyMember
                member = CompanyMember.objects.filter(user=request.user).first()
                if member:
                    sub = getattr(member.company, 'subscription', None)
                    if sub and not sub.is_active:
                        # AJAX запросы возвращают JSON
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                           request.headers.get('HX-Request'):
                            from django.http import JsonResponse
                            return JsonResponse({'error': 'subscription_expired', 'redirect': '/dashboard/subscription/'}, status=402)
                        return redirect('/dashboard/subscription/')
        return self.get_response(request)
