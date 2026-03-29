from django.urls import path
from . import views

app_name = 'companies'

urlpatterns = [
    path('register/', views.register_company, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    # Cards
    path('cards/order/', views.order_cards, name='order_cards'),
    path('cards/order/<slug:product_slug>/', views.order_cards_checkout, name='order_checkout'),
    path('payment/return/', views.payment_return, name='payment_return'),
    path('payment/cancel/', views.payment_cancel, name='payment_cancel'),
    path('orders/<int:pk>/upload-pop/', views.upload_pop, name='upload_pop'),
    path('orders/', views.orders, name='orders'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('orders/<int:pk>/retry-payment/', views.retry_payment, name='retry_payment'),
    # Assignments
    path('assignments/', views.card_assignments, name='card_assignments'),
    path('assignments/<int:pk>/assign/', views.assign_card, name='assign_card'),
    path('assignments/<int:pk>/unassign/', views.unassign_card, name='unassign_card'),
    # Employees
    path('employees/', views.employees, name='employees'),
    path('employees/invite/', views.invite_employees, name='invite'),
    path('employees/<int:pk>/edit/', views.edit_employee, name='edit_employee'),
    path('employees/<int:pk>/remove/', views.remove_employee, name='remove_employee'),
    # Settings
    path('settings/', views.company_settings, name='settings'),
    path('profile/', views.user_profile, name='user_profile'),
    path('password/', views.change_password, name='change_password'),
    # Billing / Subscription
    path('billing/', views.company_billing, name='billing'),
    path('billing/subscribe/<slug:plan_slug>/', views.company_subscribe, name='subscribe'),
    path('billing/paypal/<slug:plan_slug>/', views.company_paypal_subscribe, name='paypal_subscribe'),
    path('billing/paypal/return/', views.company_paypal_return, name='paypal_return'),
    path('billing/paypal/cancel/', views.company_paypal_cancel_return, name='paypal_cancel_return'),
    path('billing/cancel/', views.company_cancel_subscription, name='cancel_subscription'),
    # Invite acceptance
    path('invite/<uuid:token>/', views.accept_invite, name='accept_invite'),
    path('invite/<uuid:token>/signup/', views.accept_invite_signup, name='accept_invite_signup'),
]
