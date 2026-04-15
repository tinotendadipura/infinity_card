from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from .forms import _email_to_username


class CustomAccountAdapter(DefaultAccountAdapter):
    """Auto-generate username from email for regular signups."""

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        if not user.username:
            user.username = _email_to_username(user.email)
        if commit:
            user.save()
        return user

    def get_login_redirect_url(self, request):
        user = request.user
        if user.is_staff or user.is_superuser:
            return '/manage/'
        if not user.account_type:
            return '/signup/account-type/'
        if user.account_type == 'business':
            from companies.views import _get_admin_membership
            if _get_admin_membership(user):
                return '/company/dashboard/'
            return '/company/register/'
        return '/dashboard/'


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Auto-generate username from email for Google/social signups."""

    def save_user(self, request, sociallogin, form=None):
        user = sociallogin.user
        if not user.username:
            user.username = _email_to_username(user.email)
        user = super().save_user(request, sociallogin, form)
        # Google provides first/last name — sync to profile display_name
        full_name = f'{user.first_name} {user.last_name}'.strip()
        if full_name and hasattr(user, 'profile'):
            profile = user.profile
            if profile.display_name == user.username or not profile.display_name:
                profile.display_name = full_name
                profile.save(update_fields=['display_name'])
        return user

    def get_login_redirect_url(self, request):
        user = request.user
        if user.is_staff or user.is_superuser:
            return '/manage/'
        if not user.account_type:
            return '/signup/account-type/'
        if user.account_type == 'business':
            from companies.views import _get_admin_membership
            if _get_admin_membership(user):
                return '/company/dashboard/'
            return '/company/register/'
        return '/dashboard/'
