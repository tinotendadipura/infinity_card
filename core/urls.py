from django.urls import path
from . import views
from profiles.views import public_catalog

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('catalog/', public_catalog, name='public_catalog'),
    path('tap/<str:card_uid>/', views.tap_redirect_proxy, name='tap_redirect'),
    path('about/', views.about, name='about'),
    path('features/', views.features, name='features'),
    path('reviews/', views.reviews, name='reviews'),
    path('pricing/', views.pricing, name='pricing'),
    path('blog/', views.blog, name='blog'),
    path('blog/<slug:slug>/', views.blog_detail, name='blog_detail'),
    path('contact/', views.contact, name='contact'),
    path('faq/', views.faq, name='faq'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
]
