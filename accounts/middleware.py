from django.shortcuts import redirect
from django.urls import reverse


class OnboardingMiddleware:
    """Redirect authenticated users who haven't completed onboarding
    to the correct signup step. Prevents accessing dashboard, billing,
    or any protected area before finishing the sign-up flow."""

    # Paths that are always accessible (no onboarding check)
    EXEMPT_PREFIXES = (
        '/login/',
        '/logout/',
        '/signup/',
        '/admin/',
        '/accounts/',       # allauth
        '/manage/',         # admin dashboard
        '/p/',              # public profiles
        '/cards/store',     # public store
        '/cards/product',   # public product pages
        '/company/invite/', # invite acceptance
        '/static/',
        '/media/',
        # Public marketing pages
        '/features',
        '/pricing',
        '/reviews',
        '/blog',
        '/contact',
        '/about',
        '/privacy',
        '/terms',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only check authenticated users
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Exempt staff and superusers from onboarding requirements
        if request.user.is_staff or request.user.is_superuser:
            return self.get_response(request)

        path = request.path

        # Allow exempt paths through without checks
        if path == '/' or any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return self.get_response(request)

        # Step 1: Must have chosen account type
        if not request.user.account_type:
            return redirect('accounts:choose_account_type')

        # Step 2 (personal): Must have chosen a category
        if request.user.account_type == 'personal':
            profile = getattr(request.user, 'profile', None)
            if profile and profile.category_id is None:
                return redirect('accounts:choose_category')

        # Step 2 (business): Must have registered a company
        if request.user.account_type == 'business':
            # Allow access to company registration page itself
            if path.startswith('/company/register'):
                return self.get_response(request)
            # Check if they have a company membership
            if not request.user.company_memberships.exists():
                return redirect('companies:register')

        return self.get_response(request)
