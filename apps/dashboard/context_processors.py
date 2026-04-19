from apps.companies.models import CompanyMember


def company_context(request):
    if not request.user.is_authenticated:
        return {}
    memberships = CompanyMember.objects.filter(user=request.user).select_related('company')
    active_id = request.session.get('active_company_id')
    return {
        'user_memberships': memberships,
        'active_company_id': active_id,
    }
