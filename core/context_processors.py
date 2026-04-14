def subscription_context(request):
    ctx = {
        'subscription_active': getattr(request, 'subscription_active', False),
        'tenant_profile': getattr(request, 'tenant_profile', None),
        'subdomain': getattr(request, 'subdomain', None),
        'is_company_member': False,
        'profile': None,
    }

    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            from companies.models import CompanyMembership
            ctx['is_company_member'] = CompanyMembership.objects.filter(
                user=request.user, is_active=True
            ).exists()
            ctx['profile'] = getattr(request.user, 'profile', None)
        except Exception:
            # Fail silently during errors (e.g., database issues during 500)
            pass

    return ctx
