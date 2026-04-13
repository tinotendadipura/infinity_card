from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import render, redirect, get_object_or_404
from .forms import SignupForm


def signup(request):
    if request.user.is_authenticated:
        if not request.user.account_type:
            return redirect('accounts:choose_account_type')
        return redirect('profiles:dashboard')

    # Preserve ?next= so we can redirect there after onboarding
    next_url = request.GET.get('next', '') or request.POST.get('next', '')

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            if next_url:
                request.session['signup_next'] = next_url
            return redirect('accounts:choose_account_type')
    else:
        form = SignupForm()

    return render(request, 'accounts/sign-up.html', {'form': form, 'next': next_url})


@login_required
def choose_account_type(request):
    """Step 2: User picks Business or Personal account type."""
    user = request.user

    # Already chose — redirect to the right place
    if user.account_type == 'business':
        return redirect('companies:register')
    if user.account_type == 'personal':
        if user.profile.category is None:
            return redirect('accounts:choose_category')
        return _signup_final_redirect(request)

    if request.method == 'POST':
        choice = request.POST.get('account_type')
        if choice in ('personal', 'business'):
            user.account_type = choice
            user.save(update_fields=['account_type'])
            if choice == 'business':
                return redirect('companies:register')
            return redirect('accounts:choose_category')

    return render(request, 'accounts/choose_account_type.html')


def _signup_final_redirect(request):
    """Redirect to the stored next URL (e.g. store) or the dashboard."""
    next_url = request.session.pop('signup_next', '')
    if next_url:
        return redirect(next_url)
    return redirect('profiles:dashboard')


@login_required
def choose_category(request):
    """Step 3 (personal only): User picks their profile category via visual cards."""
    from categories.models import Category

    user = request.user
    if user.account_type != 'personal':
        return redirect('accounts:choose_account_type')

    # Hardcoded valid category slugs for validation (matches template)
    VALID_CATEGORIES = [
        'personal', 'business', 'creative', 'freelancer',
        'restaurant', 'real_estate', 'technology', 'healthcare'
    ]

    if request.method == 'POST':
        cat_slug = request.POST.get('category')
        if cat_slug not in VALID_CATEGORIES:
            return redirect('accounts:choose_category')
        # Get or create category to satisfy FK constraint
        category, _ = Category.objects.get_or_create(
            slug=cat_slug,
            defaults={
                'name': cat_slug.replace('_', ' ').title(),
                'description': ''
            }
        )
        profile = user.profile
        profile.category = category
        profile.save(update_fields=['category'])
        return _signup_final_redirect(request)

    return render(request, 'accounts/choose_category.html')


class CustomLoginView(LoginView):
    template_name = 'accounts/sign-in.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        # If user hasn't chosen account type yet, send them to onboarding
        if not self.request.user.account_type:
            return '/signup/account-type/'
        if self.request.user.account_type == 'business':
            from companies.views import _get_admin_membership
            if _get_admin_membership(self.request.user):
                return '/company/dashboard/'
        return super().get_success_url()


def logout_view(request):
    logout(request)
    return redirect('core:home')
