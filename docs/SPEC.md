# InfinityCard – MVP Technical Specification

> Django-based NFC Digital Identity Platform
> Version: 1.0 | Last Updated: 2026-02-27

---

## 1. Overview

InfinityCard is a shared-database, subdomain-isolated digital identity platform.
Users receive NFC-enabled cards that resolve to personal profile pages via `{username}.infinitycard.app`.

**One card. One tap. Infinite identity.**

---

## 2. Hard Constraints

| Constraint            | Rule                                      |
|-----------------------|-------------------------------------------|
| Backend               | Django 6.x, Python 3.11+                  |
| Frontend              | Django Templates only — no React/Vue/SPA  |
| JavaScript            | Vanilla JS only, minimal, non-blocking    |
| Database              | PostgreSQL (single shared DB)             |
| Multitenancy          | Subdomain-based, query-level isolation    |
| Target Load Time      | < 1 second on mobile (profile pages)      |
| Design Philosophy     | Mobile-first, single-column, minimal UI   |

---

## 3. Architecture

### 3.1 Subdomain Routing

```
Pattern:  {username}.infinitycard.app
Tap URL:  tap.infinitycard.app/{card_uid}
```

**Resolution flow:**

1. Middleware extracts subdomain from `request.get_host()`
2. Lookup `User` by `username == subdomain`
3. Attach `user` and `profile` to `request`
4. If no match → 404
5. If profile unpublished or subscription expired → inactive page

### 3.2 Project Structure

```
infinity_cards/              # Django project package (settings, urls, wsgi, asgi)
accounts/                    # Custom user model, auth views, signup/login
profiles/                    # Profile model, public profile rendering
categories/                  # Category model, category-specific extension models
cards/                       # NFC card model, tap redirect logic
subscriptions/               # Plan/subscription models, enforcement middleware
themes/                      # Theme model, CSS variable injection
analytics/                   # Tap tracking model, dashboard queries
core/                        # Shared utilities, middleware, context processors
templates/                   # Project-level templates
  ├── base.html
  ├── accounts/
  ├── profiles/
  │   ├── _base_profile.html
  │   ├── business.html
  │   ├── freelancer.html
  │   ├── real_estate.html
  │   ├── restaurant.html
  │   ├── creative.html
  │   ├── events.html
  │   └── personal.html
  ├── cards/
  ├── subscriptions/
  └── dashboard/
static/
  ├── css/
  ├── js/
  └── images/
media/
manage.py
```

---

## 4. Data Models

### 4.1 `accounts.User` (extends `AbstractUser`)

| Field         | Type          | Notes                              |
|---------------|---------------|------------------------------------|
| username      | CharField(30) | Unique. Used as subdomain slug.    |
| email         | EmailField    | Unique. Required.                  |
| password      | –             | Inherited from AbstractUser.       |
| is_active     | BooleanField  | Inherited. Controls login access.  |
| date_joined   | DateTimeField | Inherited. Auto-set.               |

**Validation:** `username` must be lowercase alphanumeric + hyphens, 3–30 chars, not in a reserved list (`www`, `admin`, `api`, `tap`, `static`, `media`).

### 4.2 `profiles.Profile`

| Field          | Type                   | Notes                                  |
|----------------|------------------------|----------------------------------------|
| user           | OneToOneField → User   | Primary key relationship.              |
| category       | ForeignKey → Category  | Determines template + fields.          |
| display_name   | CharField(100)         |                                        |
| headline       | CharField(200)         | Tagline / short description.           |
| bio            | TextField              | Max ~500 words recommended.            |
| profile_image  | ImageField             | Upload to `media/profiles/`.           |
| phone          | CharField(20)          | Optional.                              |
| email          | EmailField             | Public contact email (≠ auth email).   |
| location       | CharField(150)         | Optional.                              |
| website_url    | URLField               | Optional.                              |
| theme          | ForeignKey → Theme     | Nullable. Falls back to default.       |
| is_published   | BooleanField           | Default `False`.                       |
| created_at     | DateTimeField          | Auto-set.                              |
| updated_at     | DateTimeField          | Auto-updated.                          |

### 4.3 `categories.Category`

| Field          | Type             | Notes                                      |
|----------------|------------------|--------------------------------------------|
| name           | CharField(100)   | e.g., "Creative"                           |
| slug           | SlugField        | Unique. Maps to template name.             |
| description    | TextField        | Admin-facing.                              |
| fields_config  | JSONField        | Defines which profile sections are enabled.|
| icon           | CharField(50)    | Optional. CSS class or emoji.              |

**MVP Seed Data (7 categories):**

| #  | Name                        | Slug          |
|----|-----------------------------|---------------|
| 1  | Business / Entrepreneur     | `business`    |
| 2  | Freelancer / Consultant     | `freelancer`  |
| 3  | Real Estate Agent           | `real_estate` |
| 4  | Restaurant / Food Business  | `restaurant`  |
| 5  | Creative (Photo/Video)      | `creative`    |
| 6  | Events (Catering/Decor)     | `events`      |
| 7  | General Personal Profile    | `personal`    |

### 4.4 Category Extension Models (in `categories/models.py`)

Each has a `ForeignKey → Profile`.

| Model               | Category     | Key Fields                                          |
|----------------------|-------------|------------------------------------------------------|
| `RealEstateProperty` | real_estate | title, address, price, bedrooms, image, description  |
| `CreativeMedia`      | creative    | title, media_type (image/video), file, url, caption  |
| `EventPackage`       | events      | name, description, price, image                      |
| `MenuItem`           | restaurant  | name, description, price, category_label, image      |

### 4.5 `cards.NFCCard`

| Field       | Type                  | Notes                           |
|-------------|-----------------------|---------------------------------|
| uid         | CharField(64)         | Unique. Written to NFC chip.    |
| profile     | ForeignKey → Profile  | Nullable until assigned.        |
| is_active   | BooleanField          | Default `False`.                |
| assigned_at | DateTimeField         | Nullable. Set on assignment.    |

### 4.6 `subscriptions.Plan`

| Field         | Type            | Notes               |
|---------------|-----------------|----------------------|
| name          | CharField(50)   | e.g., "Starter"     |
| slug          | SlugField       | Unique.              |
| price         | DecimalField    | Monthly price (USD). |
| features      | JSONField       | Feature flags dict.  |

**MVP Plans:** Starter ($3), Business ($5), Pro ($10)

### 4.7 `subscriptions.Subscription`

| Field      | Type                 | Notes                                       |
|------------|----------------------|----------------------------------------------|
| user       | OneToOneField → User | One active subscription per user.            |
| plan       | ForeignKey → Plan    |                                              |
| status     | CharField            | Choices: `active`, `expired`, `suspended`.   |
| started_at | DateTimeField        |                                              |
| expires_at | DateTimeField        |                                              |

### 4.8 `themes.Theme`

| Field            | Type           | Notes                    |
|------------------|----------------|--------------------------|
| name             | CharField(50)  |                          |
| primary_color    | CharField(7)   | Hex. e.g., `#1A73E8`    |
| secondary_color  | CharField(7)   |                          |
| background_color | CharField(7)   |                          |
| text_color       | CharField(7)   |                          |
| is_default       | BooleanField   | Exactly one is default.  |

### 4.9 `analytics.TapEvent`

| Field      | Type                  | Notes                           |
|------------|-----------------------|---------------------------------|
| profile    | ForeignKey → Profile  |                                 |
| timestamp  | DateTimeField         | Auto-set.                       |
| ip_address | GenericIPAddressField |                                 |
| user_agent | TextField             |                                 |
| country    | CharField(100)        | Optional. Derived from IP.      |

---

## 5. Middleware Stack (Custom)

| Middleware               | App           | Purpose                                              |
|--------------------------|---------------|------------------------------------------------------|
| `SubdomainMiddleware`    | core          | Extracts subdomain, attaches `request.tenant_user`.  |
| `SubscriptionMiddleware` | subscriptions | Checks subscription, sets `request.subscription_active`. |

**Placement:** After `AuthenticationMiddleware` in the `MIDDLEWARE` list.

---

## 6. URL Scheme

### Main Domain (`infinitycard.app`)

| Path                     | View                      | Notes                    |
|--------------------------|---------------------------|--------------------------|
| `/`                      | Landing page              |                          |
| `/signup/`               | Registration              |                          |
| `/login/`                | Login                     |                          |
| `/logout/`               | Logout                    |                          |
| `/dashboard/`            | User dashboard            | Auth required.           |
| `/dashboard/profile/`    | Edit profile              | Auth required.           |
| `/dashboard/analytics/`  | View tap stats            | Auth required.           |
| `/admin/`                | Django admin              |                          |

### Tap Domain (`tap.infinitycard.app`)

| Path            | View           | Notes                                  |
|-----------------|----------------|----------------------------------------|
| `/{card_uid}/`  | Tap redirect   | Validates card → redirects to subdomain. |

### Subdomain (`{username}.infinitycard.app`)

| Path  | View           | Notes                                     |
|-------|----------------|-------------------------------------------|
| `/`   | Public profile | Rendered with category-specific template. |

---

## 7. Request Lifecycle: NFC Tap

```
NFC Tap
  → Phone opens: https://tap.infinitycard.app/{card_uid}
  → cards.views.tap_redirect(request, card_uid)
      → Lookup NFCCard by uid
      → IF not found → 404
      → IF not active → render inactive page
      → Log TapEvent (ip, user_agent, timestamp)
      → Check subscription status
      → 302 redirect → https://{username}.infinitycard.app
  → SubdomainMiddleware resolves profile
  → Render category template with theme CSS variables
```

---

## 8. Template Rendering Strategy

### Theme Injection (in base profile template)

```html
<style>
  :root {
    --color-primary: {{ profile.theme.primary_color|default:"#1A73E8" }};
    --color-secondary: {{ profile.theme.secondary_color|default:"#FF6D00" }};
    --color-bg: {{ profile.theme.background_color|default:"#FFFFFF" }};
    --color-text: {{ profile.theme.text_color|default:"#212121" }};
  }
</style>
```

### Template Resolution

```python
def public_profile(request):
    profile = request.tenant_profile
    template = f"profiles/{profile.category.slug}.html"
    return render(request, template, {"profile": profile})
```

All category templates extend `profiles/_base_profile.html`.

---

## 9. Admin Customization

Register all models with `django.contrib.admin`. Key admin actions:

- **Users:** View, activate/deactivate
- **NFC Cards:** Assign to profile, bulk import UIDs
- **Subscriptions:** Change plan, extend expiry, suspend
- **Analytics:** Read-only list view, filters by profile/date
- **Categories & Themes:** Full CRUD

---

## 10. Security Checklist

- [x] HTTPS enforced (Nginx + Let's Encrypt)
- [x] CSRF on all forms (Django default)
- [x] `SECURE_BROWSER_XSS_FILTER = True`
- [x] `SECURE_CONTENT_TYPE_NOSNIFF = True`
- [x] `X_FRAME_OPTIONS = "DENY"`
- [x] Password hashing (Django PBKDF2 default)
- [x] Rate limiting on `/tap/{uid}/` (django-ratelimit or Nginx)
- [x] Media files served through Nginx, not Django
- [x] Reserved subdomain list enforced at registration
- [x] `DEBUG = False` in production

---

## 11. Performance Targets

| Metric              | Target        | Method                             |
|---------------------|---------------|------------------------------------|
| Profile page TTFB   | < 200ms       | Optimized queries, select_related  |
| Profile page load   | < 1s (3G)     | Minimal assets, lazy images        |
| Image size          | < 200KB       | Server-side resize on upload       |
| Static assets       | Cached 30d    | Nginx cache headers, fingerprinting|
| Gzip                | Enabled       | Nginx gzip on text/* responses     |

---

## 12. Deployment Topology

```
Client (NFC Tap / Browser)
  │
  ▼
Nginx (wildcard SSL, static/media, reverse proxy)
  │
  ▼
Gunicorn (WSGI, 4 workers)
  │
  ▼
Django Application
  │
  ▼
PostgreSQL
```

### DNS Records

```
A     infinitycard.app        → VPS_IP
A     *.infinitycard.app      → VPS_IP
A     tap.infinitycard.app    → VPS_IP
```

---

## 13. Phase 2 Hooks (Not in MVP – Design for Later)

- Custom domains per user
- Team/organization profiles
- White-label deployments
- Content hosting (courses, sermons)
- REST API (`/api/v1/`)
- CRM integrations
- Payment gateway integration (Stripe/Paystack)

> **MVP rule:** No code for Phase 2, but no design decisions that block it.
