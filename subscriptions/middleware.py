from subscriptions.models import Subscription


def check_user_subscription(user):
    """
    Check subscription status for any user (personal or company).

    Returns a dict:
        active (bool): True if the user has a valid, non-expired subscription
        reason (str|None): 'no_subscription', 'expired', 'cancelled', 'suspended', or None if active
        is_company (bool): True if the user's subscription is via a company
        owner_name (str): Display name of the subscription owner (company name or user display name)
    """
    result = {
        'active': False,
        'reason': 'no_subscription',
        'is_company': False,
        'owner_name': '',
    }

    # 1) Check if user belongs to an active company membership
    membership = (
        user.company_memberships
        .filter(is_active=True)
        .select_related('company')
        .first()
    )

    if membership:
        result['is_company'] = True
        result['owner_name'] = membership.company.name
        try:
            sub = membership.company.subscription
            if sub.is_active():
                result['active'] = True
                result['reason'] = None
            elif sub.status == 'cancelled':
                result['reason'] = 'cancelled'
            elif sub.status == 'suspended':
                result['reason'] = 'suspended'
            else:
                result['reason'] = 'expired'
        except Exception:
            result['reason'] = 'no_subscription'
        return result

    # 2) Personal subscription
    profile = getattr(user, 'profile', None)
    result['owner_name'] = profile.display_name if profile else user.get_full_name() or user.username
    try:
        sub = user.subscription
        if sub.is_active():
            result['active'] = True
            result['reason'] = None
        elif sub.status == 'cancelled':
            result['reason'] = 'cancelled'
        elif sub.status == 'suspended':
            result['reason'] = 'suspended'
        else:
            result['reason'] = 'expired'
    except Subscription.DoesNotExist:
        result['reason'] = 'no_subscription'

    return result


class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.subscription_active = False
        request.subscription_info = None
        if hasattr(request, 'tenant_user') and request.tenant_user:
            info = check_user_subscription(request.tenant_user)
            request.subscription_active = info['active']
            request.subscription_info = info
        return self.get_response(request)
