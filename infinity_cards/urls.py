from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from profiles.views import public_profile, preview_profile, public_catalog_preview, public_catalog, public_profile_by_code
from core.views import error_404, error_500, error_403

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('accounts.urls')),
    path('dashboard/', include('profiles.urls')),
    # Public profile via simple URL: /p/<username>/<code>/
    path('p/<str:username>/<str:code>/', public_profile, name='public_profile'),
    # Public catalog via simple URL: /p/<username>/catalog/
    path('p/<str:username>/catalog/', public_catalog_preview, name='public_catalog_preview'),
    # Legacy preview URL (for backward compatibility)
    path('p/<str:username>/', preview_profile, name='preview_profile'),
    # Catalog at root level (for subdomain backward compatibility)
    path('catalog/', public_catalog, name='public_catalog'),
    path('', include('subscriptions.urls')),
    path('cards/', include('cards.urls')),
    path('company/', include('companies.urls')),
    path('', include('core.urls')),
    path('analytics/', include('analytics.urls')),
    # Public profile via subdomain + code: username.inftycard.cc/code/
    path('<str:code>/', public_profile_by_code, name='public_profile_by_code'),
]

# Custom error handlers
handler404 = 'core.views.error_404'
handler500 = 'core.views.error_500'
handler403 = 'core.views.error_403'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Test error pages in development
    urlpatterns += [
        path('__test404__/', error_404, name='test_404'),
        path('__test500__/', error_500, name='test_500'),
        path('__test403__/', error_403, name='test_403'),
    ]
