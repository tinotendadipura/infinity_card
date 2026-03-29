# InfinityCard – Developer Build Guide

> Step-by-step implementation plan for the MVP
> Target: Single developer, sequential execution
> Version: 1.0 | Last Updated: 2026-02-27

---

## Prerequisites

- Python 3.11+
- PostgreSQL 14+ running locally
- Database: `infinitycards` (already created)
- Git initialized
- Virtual environment created (`venv/`)
- Django 6.0.2 installed
- psycopg[binary] installed

---

## Phase 1: Project Scaffolding

### Step 1.1 — Create Django Apps

```bash
python manage.py startapp accounts
python manage.py startapp profiles
python manage.py startapp categories
python manage.py startapp cards
python manage.py startapp subscriptions
python manage.py startapp themes
python manage.py startapp analytics
```

Register all apps in `INSTALLED_APPS` (settings.py):

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Project apps
    'accounts',
    'profiles',
    'categories',
    'cards',
    'subscriptions',
    'themes',
    'analytics',
    'core',
]
```

### Step 1.2 — Install Additional Dependencies

```bash
pip install Pillow            # ImageField support
pip install django-ratelimit  # Rate limiting on tap endpoint
```

Update `requirements.txt` after each install.

### Step 1.3 — Settings Configuration

Add to `settings.py`:

```python
AUTH_USER_MODEL = 'accounts.User'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.infinitycard.app', '.infinitycard.local']

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
```

### Step 1.4 — Create Directory Structure

```
templates/
  ├── accounts/
  ├── profiles/
  ├── cards/
  ├── subscriptions/
  └── dashboard/
static/
  ├── css/
  ├── js/
  └── images/
media/
  └── profiles/
```

---

## Phase 2: Custom User Model (`accounts`)

> ⚠️ **CRITICAL:** Must be done before first `migrate` with the new app set.
> Since we already ran migrations with the default user model, we MUST reset the database first.

### Step 2.1 — Reset Database

```sql
-- Run in psql or pgAdmin:
DROP DATABASE infinitycards;
CREATE DATABASE infinitycards;
```

### Step 2.2 — Define `accounts/models.py`

```python
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


class User(AbstractUser):
    username = models.CharField(
        max_length=30,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$',
                message='Lowercase letters, numbers, and hyphens only. '
                        'Must start and end with a letter or number.',
            ),
        ],
    )
    email = models.EmailField(unique=True)

    RESERVED_USERNAMES = {
        'www', 'admin', 'api', 'tap', 'static', 'media',
        'mail', 'ftp', 'dashboard', 'login', 'logout', 'signup',
    }

    def clean(self):
        super().clean()
        if self.username.lower() in self.RESERVED_USERNAMES:
            from django.core.exceptions import ValidationError
            raise ValidationError({'username': 'This username is reserved.'})

    def __str__(self):
        return self.username
```

### Step 2.3 — Register Admin

```python
# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_active', 'date_joined')
    search_fields = ('username', 'email')
```

### Step 2.4 — Migrate & Create Superuser

```bash
python manage.py makemigrations accounts
python manage.py migrate
python manage.py createsuperuser
```

---

## Phase 3: Themes (`themes`)

> Build themes before profiles, since `Profile` has a ForeignKey to `Theme`.

### Step 3.1 — Define `themes/models.py`

```python
from django.db import models


class Theme(models.Model):
    name = models.CharField(max_length=50)
    primary_color = models.CharField(max_length=7, default='#1A73E8')
    secondary_color = models.CharField(max_length=7, default='#FF6D00')
    background_color = models.CharField(max_length=7, default='#FFFFFF')
    text_color = models.CharField(max_length=7, default='#212121')
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
```

### Step 3.2 — Admin Registration

```python
# themes/admin.py
from django.contrib import admin
from .models import Theme


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ('name', 'primary_color', 'is_default')
    list_editable = ('is_default',)
```

### Step 3.3 — Seed Default Themes (Management Command)

Create file: `themes/management/commands/seed_themes.py`

```python
from django.core.management.base import BaseCommand
from themes.models import Theme


class Command(BaseCommand):
    help = 'Seed default themes'

    def handle(self, *args, **options):
        themes = [
            {
                'name': 'Ocean Blue',
                'primary_color': '#1A73E8',
                'secondary_color': '#FF6D00',
                'background_color': '#FFFFFF',
                'text_color': '#212121',
                'is_default': True,
            },
            {
                'name': 'Midnight',
                'primary_color': '#BB86FC',
                'secondary_color': '#03DAC6',
                'background_color': '#121212',
                'text_color': '#E0E0E0',
            },
            {
                'name': 'Forest',
                'primary_color': '#2E7D32',
                'secondary_color': '#FF8F00',
                'background_color': '#F1F8E9',
                'text_color': '#1B5E20',
            },
            {
                'name': 'Sunset',
                'primary_color': '#E65100',
                'secondary_color': '#AD1457',
                'background_color': '#FFF3E0',
                'text_color': '#3E2723',
            },
        ]
        for t in themes:
            Theme.objects.update_or_create(name=t['name'], defaults=t)
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(themes)} themes'))
```

### Step 3.4 — Migrate & Seed

```bash
python manage.py makemigrations themes
python manage.py migrate
python manage.py seed_themes
```

---

## Phase 4: Categories (`categories`)

### Step 4.1 — Define `categories/models.py`

```python
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    fields_config = models.JSONField(
        default=dict,
        help_text='Defines enabled sections for this category template',
    )
    icon = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name
```

### Step 4.2 — Admin Registration

```python
# categories/admin.py
from django.contrib import admin
from .models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
```

### Step 4.3 — Seed Categories (Management Command)

Create file: `categories/management/commands/seed_categories.py`

```python
from django.core.management.base import BaseCommand
from categories.models import Category


class Command(BaseCommand):
    help = 'Seed MVP categories'

    def handle(self, *args, **options):
        categories = [
            {
                'name': 'Business / Entrepreneur',
                'slug': 'business',
                'description': 'For business owners and entrepreneurs.',
                'fields_config': {
                    'sections': ['bio', 'services', 'contact', 'social_links', 'cta'],
                    'cta_label': 'Get in Touch',
                },
            },
            {
                'name': 'Freelancer / Consultant',
                'slug': 'freelancer',
                'description': 'For freelancers, consultants, and independent professionals.',
                'fields_config': {
                    'sections': ['bio', 'skills', 'portfolio', 'contact', 'social_links', 'cta'],
                    'cta_label': 'Hire Me',
                },
            },
            {
                'name': 'Real Estate Agent',
                'slug': 'real_estate',
                'description': 'For real estate agents and property managers.',
                'fields_config': {
                    'sections': ['bio', 'listings', 'contact', 'social_links', 'cta'],
                    'cta_label': 'View Listings',
                },
            },
            {
                'name': 'Restaurant / Food Business',
                'slug': 'restaurant',
                'description': 'For restaurants, cafes, and food businesses.',
                'fields_config': {
                    'sections': ['bio', 'menu', 'hours', 'location', 'contact', 'cta'],
                    'cta_label': 'Order Now',
                },
            },
            {
                'name': 'Creative (Photo/Video)',
                'slug': 'creative',
                'description': 'For photographers, videographers, and visual creatives.',
                'fields_config': {
                    'sections': ['bio', 'gallery', 'services', 'contact', 'social_links', 'cta'],
                    'cta_label': 'Book a Session',
                },
            },
            {
                'name': 'Events (Catering/Decor)',
                'slug': 'events',
                'description': 'For event planners, caterers, and decor specialists.',
                'fields_config': {
                    'sections': ['bio', 'packages', 'gallery', 'contact', 'social_links', 'cta'],
                    'cta_label': 'Get a Quote',
                },
            },
            {
                'name': 'General Personal Profile',
                'slug': 'personal',
                'description': 'A general-purpose personal profile.',
                'fields_config': {
                    'sections': ['bio', 'contact', 'social_links'],
                    'cta_label': 'Connect',
                },
            },
        ]
        for c in categories:
            Category.objects.update_or_create(slug=c['slug'], defaults=c)
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(categories)} categories'))
```

### Step 4.4 — Migrate & Seed

```bash
python manage.py makemigrations categories
python manage.py migrate
python manage.py seed_categories
```

---

## Phase 5: Profiles + Category Extensions

### Step 5.1 — Define `profiles/models.py`

```python
from django.conf import settings
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    category = models.ForeignKey(
        'categories.Category',
        on_delete=models.SET_NULL,
        null=True,
    )
    display_name = models.CharField(max_length=100)
    headline = models.CharField(max_length=200, blank=True)
    bio = models.TextField(blank=True)
    profile_image = models.ImageField(upload_to='profiles/', blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True, help_text='Public contact email')
    location = models.CharField(max_length=150, blank=True)
    website_url = models.URLField(blank=True)
    theme = models.ForeignKey(
        'themes.Theme',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.display_name} ({self.user.username})'

    def get_absolute_url(self):
        return f'https://{self.user.username}.infinitycard.app'
```

### Step 5.2 — Admin Registration

```python
# profiles/admin.py
from django.contrib import admin
from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'category', 'is_published', 'updated_at')
    list_filter = ('is_published', 'category')
    search_fields = ('display_name', 'user__username')
    raw_id_fields = ('user',)
```

### Step 5.3 — Category Extension Models (append to `categories/models.py`)

```python
class RealEstateProperty(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile', on_delete=models.CASCADE, related_name='properties',
    )
    title = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    bedrooms = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='categories/real_estate/', blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'real estate properties'

    def __str__(self):
        return self.title


class CreativeMedia(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile', on_delete=models.CASCADE, related_name='media_items',
    )
    title = models.CharField(max_length=200)
    media_type = models.CharField(
        max_length=10,
        choices=[('image', 'Image'), ('video', 'Video')],
    )
    file = models.FileField(upload_to='categories/creative/', blank=True)
    url = models.URLField(blank=True, help_text='External embed URL (YouTube, Vimeo)')
    caption = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'creative media'

    def __str__(self):
        return self.title


class EventPackage(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile', on_delete=models.CASCADE, related_name='event_packages',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='categories/events/', blank=True)

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile', on_delete=models.CASCADE, related_name='menu_items',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    category_label = models.CharField(
        max_length=50, blank=True,
        help_text='e.g., Starters, Mains, Desserts',
    )
    image = models.ImageField(upload_to='categories/restaurant/', blank=True)

    def __str__(self):
        return self.name
```

### Step 5.4 — Register Extension Admin

```python
# categories/admin.py (append)
from .models import RealEstateProperty, CreativeMedia, EventPackage, MenuItem

@admin.register(RealEstateProperty)
class RealEstatePropertyAdmin(admin.ModelAdmin):
    list_display = ('title', 'profile', 'price')

@admin.register(CreativeMedia)
class CreativeMediaAdmin(admin.ModelAdmin):
    list_display = ('title', 'profile', 'media_type')

@admin.register(EventPackage)
class EventPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'profile', 'price')

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'profile', 'price', 'category_label')
```

### Step 5.5 — Migrate

```bash
python manage.py makemigrations profiles categories
python manage.py migrate
```

---

## Phase 6: NFC Cards (`cards`)

### Step 6.1 — Define `cards/models.py`

```python
from django.db import models


class NFCCard(models.Model):
    uid = models.CharField(max_length=64, unique=True, db_index=True)
    profile = models.ForeignKey(
        'profiles.Profile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='nfc_cards',
    )
    is_active = models.BooleanField(default=False)
    assigned_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Card {self.uid} → {self.profile or "Unassigned"}'
```

### Step 6.2 — Tap Redirect View (`cards/views.py`)

```python
from django.shortcuts import get_object_or_404, redirect, render
from .models import NFCCard
from analytics.models import TapEvent


def tap_redirect(request, card_uid):
    card = get_object_or_404(NFCCard, uid=card_uid)

    if not card.is_active or not card.profile:
        return render(request, 'cards/inactive.html', status=200)

    TapEvent.objects.create(
        profile=card.profile,
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )

    username = card.profile.user.username
    return redirect(f'https://{username}.infinitycard.app')
```

### Step 6.3 — URL Config (`cards/urls.py`)

```python
from django.urls import path
from . import views

app_name = 'cards'

urlpatterns = [
    path('<str:card_uid>/', views.tap_redirect, name='tap_redirect'),
]
```

### Step 6.4 — Admin Registration

```python
# cards/admin.py
from django.contrib import admin
from .models import NFCCard


@admin.register(NFCCard)
class NFCCardAdmin(admin.ModelAdmin):
    list_display = ('uid', 'profile', 'is_active', 'assigned_at')
    list_filter = ('is_active',)
    search_fields = ('uid', 'profile__user__username')
    raw_id_fields = ('profile',)
```

### Step 6.5 — Migrate

```bash
python manage.py makemigrations cards
python manage.py migrate
```

---

## Phase 7: Subscriptions (`subscriptions`)

### Step 7.1 — Define `subscriptions/models.py`

```python
from django.conf import settings
from django.db import models
from django.utils import timezone


class Plan(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    features = models.JSONField(default=dict)

    def __str__(self):
        return f'{self.name} (${self.price}/mo)'

    class Meta:
        ordering = ['price']


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_active(self):
        return self.status == 'active' and self.expires_at > timezone.now()

    def __str__(self):
        return f'{self.user.username} – {self.plan.name} ({self.status})'
```

### Step 7.2 — Subscription Enforcement Middleware

Create file: `subscriptions/middleware.py`

```python
from subscriptions.models import Subscription


class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.subscription_active = False
        if hasattr(request, 'tenant_user') and request.tenant_user:
            try:
                sub = request.tenant_user.subscription
                request.subscription_active = sub.is_active()
            except Subscription.DoesNotExist:
                pass
        return self.get_response(request)
```

### Step 7.3 — Admin Registration

```python
# subscriptions/admin.py
from django.contrib import admin
from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'price')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'started_at', 'expires_at')
    list_filter = ('status', 'plan')
    search_fields = ('user__username',)
    raw_id_fields = ('user',)
```

### Step 7.4 — Seed Plans (Management Command)

Create file: `subscriptions/management/commands/seed_plans.py`

```python
from django.core.management.base import BaseCommand
from subscriptions.models import Plan


class Command(BaseCommand):
    help = 'Seed MVP subscription plans'

    def handle(self, *args, **options):
        plans = [
            {
                'name': 'Starter',
                'slug': 'starter',
                'price': 3.00,
                'features': {'max_images': 5, 'analytics': False},
            },
            {
                'name': 'Business',
                'slug': 'business',
                'price': 5.00,
                'features': {'max_images': 20, 'analytics': True},
            },
            {
                'name': 'Pro',
                'slug': 'pro',
                'price': 10.00,
                'features': {'max_images': 50, 'analytics': True, 'custom_theme': True},
            },
        ]
        for p in plans:
            Plan.objects.update_or_create(slug=p['slug'], defaults=p)
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(plans)} plans'))
```

### Step 7.5 — Migrate & Seed

```bash
python manage.py makemigrations subscriptions
python manage.py migrate
python manage.py seed_plans
```

---

## Phase 8: Analytics (`analytics`)

### Step 8.1 — Define `analytics/models.py`

```python
from django.db import models


class TapEvent(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile',
        on_delete=models.CASCADE,
        related_name='tap_events',
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['profile', '-timestamp']),
        ]

    def __str__(self):
        return f'Tap on {self.profile} at {self.timestamp}'
```

### Step 8.2 — Admin Registration

```python
# analytics/admin.py
from django.contrib import admin
from .models import TapEvent


@admin.register(TapEvent)
class TapEventAdmin(admin.ModelAdmin):
    list_display = ('profile', 'timestamp', 'ip_address', 'country')
    list_filter = ('timestamp',)
    search_fields = ('profile__user__username',)
    readonly_fields = ('profile', 'timestamp', 'ip_address', 'user_agent', 'country')
```

### Step 8.3 — Migrate

```bash
python manage.py makemigrations analytics
python manage.py migrate
```

---

## Phase 9: Core Middleware & Utilities (`core`)

### Step 9.1 — Subdomain Middleware

Create/update file: `core/middleware.py`

```python
from accounts.models import User


class SubdomainMiddleware:
    IGNORED_SUBDOMAINS = {'www', 'tap', ''}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0]
        parts = host.split('.')

        request.subdomain = None
        request.tenant_user = None
        request.tenant_profile = None

        if len(parts) >= 3:
            subdomain = parts[0].lower()
            if subdomain not in self.IGNORED_SUBDOMAINS:
                request.subdomain = subdomain
                try:
                    user = User.objects.select_related(
                        'profile__category', 'profile__theme',
                    ).get(username=subdomain)
                    request.tenant_user = user
                    request.tenant_profile = getattr(user, 'profile', None)
                except User.DoesNotExist:
                    pass

        return self.get_response(request)
```

### Step 9.2 — Register Middleware in `settings.py`

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Custom
    'core.middleware.SubdomainMiddleware',
    'subscriptions.middleware.SubscriptionMiddleware',
]
```

---

## Phase 10: Templates & Views

### Step 10.1 — Base Template (`templates/base.html`)

Build a full HTML5 shell:
- Viewport meta tag for mobile
- Theme CSS variable injection block
- `{% block title %}`, `{% block content %}`, `{% block extra_head %}`
- Minimal global nav (login/logout/dashboard)
- Footer

### Step 10.2 — Profile Base Template (`templates/profiles/_base_profile.html`)

Extends `base.html`. Contains:
- Theme CSS variables from `profile.theme`
- Profile image (lazy loaded)
- Display name + headline
- Bio section
- Contact section (phone, email, website, location)
- `{% block category_content %}` — overridden per category

### Step 10.3 — Category Templates (one per slug)

Each extends `_base_profile.html` and fills `{% block category_content %}`:

| Template File                        | Category-Specific Content               |
|--------------------------------------|-----------------------------------------|
| `templates/profiles/business.html`   | Services list, CTA button               |
| `templates/profiles/freelancer.html` | Skills, portfolio links, hire CTA       |
| `templates/profiles/real_estate.html`| Property listings grid                  |
| `templates/profiles/restaurant.html` | Menu grouped by category, order CTA     |
| `templates/profiles/creative.html`   | Image/video gallery, booking CTA        |
| `templates/profiles/events.html`     | Event packages grid, quote CTA          |
| `templates/profiles/personal.html`   | Simple bio + contact info               |

### Step 10.4 — Public Profile View (`profiles/views.py`)

```python
from django.http import Http404
from django.shortcuts import render


def public_profile(request):
    profile = request.tenant_profile
    if not profile or not profile.is_published:
        raise Http404

    template = f'profiles/{profile.category.slug}.html'
    context = {
        'profile': profile,
        'subscription_active': request.subscription_active,
    }

    slug = profile.category.slug
    if slug == 'real_estate':
        context['properties'] = profile.properties.all()
    elif slug == 'creative':
        context['media_items'] = profile.media_items.all()
    elif slug == 'events':
        context['packages'] = profile.event_packages.all()
    elif slug == 'restaurant':
        context['menu_items'] = profile.menu_items.all()

    return render(request, template, context)
```

### Step 10.5 — Account Views (`accounts/views.py`)

Implement:
- **`signup`** — Registration form with username validation + category picker
- **`login_view`** — Django `LoginView` or custom
- **`logout_view`** — Django `LogoutView`, redirect to landing

### Step 10.6 — Dashboard Views

Implement in `profiles/views.py` or a dedicated module:
- **`dashboard_home`** — Overview: tap count, subscription status, profile link
- **`edit_profile`** — ModelForm for Profile fields
- **`analytics_view`** — Table/chart of recent taps

---

## Phase 11: URL Wiring

### Project URLs (`infinity_cards/urls.py`)

```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('', include('accounts.urls')),
    path('dashboard/', include('profiles.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### App URL Files to Create

| File                     | Key Routes                                   |
|--------------------------|----------------------------------------------|
| `core/urls.py`           | `/` (landing page)                           |
| `accounts/urls.py`       | `/signup/`, `/login/`, `/logout/`            |
| `profiles/urls.py`       | `/dashboard/`, `/dashboard/profile/`, `/dashboard/analytics/` |
| `cards/urls.py`          | `/{card_uid}/` (tap redirect, mounted on tap subdomain) |

---

## Phase 12: Static Assets & CSS

### Step 12.1 — Global CSS (`static/css/main.css`)

- CSS reset / normalize
- CSS custom properties mapped to theme variables
- Single-column, max-width container
- Mobile-first responsive breakpoints
- Typography scale: large, readable, high contrast
- Button styles: min 44px tap target, thumb-friendly

### Step 12.2 — Profile CSS (`static/css/profile.css`)

- Profile card layout
- Circular image crop
- Section spacing
- CTA button styles
- Gallery grid (for creative/events)

---

## Phase 13: Local Development — Subdomain Testing

### Edit Windows hosts file

Path: `C:\Windows\System32\drivers\etc\hosts`

```
127.0.0.1   infinitycard.local
127.0.0.1   john.infinitycard.local
127.0.0.1   tap.infinitycard.local
```

### Update `ALLOWED_HOSTS`

```python
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.infinitycard.local']
```

### Run dev server on port 8000

```bash
python manage.py runserver 0.0.0.0:8000
```

Access profiles at: `http://john.infinitycard.local:8000/`

---

## Build Order Summary

| #  | Phase                       | Depends On | Status |
|----|-----------------------------|------------|--------|
| 1  | Project scaffolding         | —          | ☐      |
| 2  | Custom User model           | 1          | ☐      |
| 3  | Themes                      | 1          | ☐      |
| 4  | Categories                  | 1          | ☐      |
| 5  | Profiles + Extensions       | 2, 3, 4   | ☐      |
| 6  | NFC Cards + Tap redirect    | 5          | ☐      |
| 7  | Subscriptions               | 2          | ☐      |
| 8  | Analytics                   | 5          | ☐      |
| 9  | Core middleware              | 2, 5, 7   | ☐      |
| 10 | Templates & Views           | All above  | ☐      |
| 11 | URL wiring                  | 10         | ☐      |
| 12 | Static assets / CSS         | 10         | ☐      |
| 13 | Local subdomain testing     | 11         | ☐      |

---

## Verification Checklist

- [ ] `python manage.py check` — no errors
- [ ] `python manage.py migrate` — all migrations clean
- [ ] Admin login works at `/admin/`
- [ ] Superuser can CRUD all models in admin
- [ ] User signup creates User + Profile
- [ ] Subdomain resolves to correct profile
- [ ] NFC tap URL logs event and redirects correctly
- [ ] Subscription middleware blocks expired profiles gracefully
- [ ] Theme CSS variables render on profile page
- [ ] All 7 category templates render with correct data
- [ ] Analytics log tap events with IP + user agent
- [ ] Mobile layout is single-column, < 1s load
- [ ] Reserved usernames are rejected at signup
