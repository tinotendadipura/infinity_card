from django.urls import path
from . import views

app_name = 'profiles'

urlpatterns = [
    path('', views.dashboard_home, name='dashboard'),
    path('update-name/', views.update_name, name='update_name'),
    path('profile/', views.edit_profile, name='edit_profile'),
    path('analytics/', views.analytics_view, name='analytics'),
    path('theme/', views.theme_picker, name='theme_picker'),
    path('theme/save/', views.theme_save_ajax, name='theme_save_ajax'),
    path('social-links/', views.social_links_view, name='social_links'),
    path('catalog/', views.catalog_view, name='catalog'),
    path('catalog/<int:item_id>/', views.catalog_item_detail, name='catalog_item_detail'),
    path('my-card/', views.my_card_view, name='my_card'),
    path('services/', views.services_view, name='services'),
    path('skills/', views.skills_view, name='skills'),
    path('experience/', views.experience_view, name='experience'),
    path('education/', views.education_view, name='education'),
    path('settings/', views.settings_view, name='settings'),
    path('settings/toggle/', views.toggle_feature, name='toggle_feature'),
    path('messages/', views.contact_messages_view, name='contact_messages'),
    path('p/<str:username>/catalog/', views.public_catalog_preview, name='public_catalog_preview'),
    path('p/<str:name_slug>/<str:code>/', views.nfc_profile_redirect, name='nfc_profile_redirect'),
    path('p/<str:username>/', views.preview_profile, name='preview_profile'),
    path('contact/<int:profile_id>/', views.submit_contact_message, name='submit_contact_message'),
]
