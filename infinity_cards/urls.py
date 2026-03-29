from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from profiles.views import nfc_profile_redirect, preview_profile, public_catalog_preview

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('accounts.urls')),
    # NFC card URL + public profile preview at root /p/ level
    path('p/<str:username>/catalog/', public_catalog_preview, name='public_catalog_preview'),
    path('p/<str:name_slug>/<str:code>/', nfc_profile_redirect, name='nfc_profile_redirect'),
    path('p/<str:username>/', preview_profile, name='preview_profile'),
    path('dashboard/', include('profiles.urls')),
    path('', include('subscriptions.urls')),
    path('cards/', include('cards.urls')),
    path('company/', include('companies.urls')),
    path('', include('core.urls')),
    path('analytics/', include('analytics.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
