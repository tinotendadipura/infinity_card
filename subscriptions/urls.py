from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('plans/', views.plans_page, name='plans'),
    path('billing/', views.billing_dashboard, name='billing'),
    path('subscribe/<slug:plan_slug>/', views.subscribe, name='subscribe'),
    path('renew/', views.renew_subscription, name='renew'),
    path('cancel/', views.cancel_subscription, name='cancel'),
    path('cancel-downgrade/', views.cancel_downgrade, name='cancel_downgrade'),
    path('upload-pop/', views.upload_subscription_pop, name='upload_subscription_pop'),
    # PayPal subscription flow
    path('paypal/subscribe/<slug:plan_slug>/', views.paypal_subscribe, name='paypal_subscribe'),
    path('paypal/return/', views.paypal_return, name='paypal_return'),
    path('paypal/cancel/', views.paypal_cancel_return, name='paypal_cancel_return'),
    path('paypal/webhook/', views.paypal_webhook, name='paypal_webhook'),

    # ── Super-admin management dashboard ──
    path('manage/', views.admin_dashboard, name='admin_dashboard'),
    # Orders
    path('manage/orders/', views.admin_orders, name='admin_orders'),
    path('manage/order/<int:order_id>/paid/', views.admin_mark_order_paid, name='admin_mark_order_paid'),
    path('manage/order/<int:order_id>/activate/', views.admin_activate_subscription, name='admin_activate_subscription'),
    path('manage/order/<int:order_id>/update/', views.admin_update_order, name='admin_update_order'),
    # Bulk orders
    path('manage/bulk-orders/', views.admin_bulk_orders, name='admin_bulk_orders'),
    path('manage/bulk-order/<int:order_id>/action/', views.admin_bulk_order_action, name='admin_bulk_order_action'),
    # Payment approvals
    path('manage/approvals/', views.admin_approvals, name='admin_approvals'),
    path('manage/approvals/personal/<int:pop_id>/approve/', views.admin_approve_personal_pop, name='admin_approve_personal_pop'),
    path('manage/approvals/personal/<int:pop_id>/reject/', views.admin_reject_personal_pop, name='admin_reject_personal_pop'),
    path('manage/approvals/cash-order/<int:order_id>/approve/', views.admin_approve_cash_order, name='admin_approve_cash_order'),
    path('manage/approvals/company-cash-order/<int:order_id>/approve/', views.admin_approve_company_cash_order, name='admin_approve_company_cash_order'),
    path('manage/approvals/company/<int:pop_id>/approve/', views.admin_approve_company_pop, name='admin_approve_company_pop'),
    path('manage/approvals/company/<int:pop_id>/reject/', views.admin_reject_company_pop, name='admin_reject_company_pop'),
    path('manage/approvals/subscription/<int:pop_id>/approve/', views.admin_approve_subscription_pop, name='admin_approve_subscription_pop'),
    path('manage/approvals/subscription/<int:pop_id>/reject/', views.admin_reject_subscription_pop, name='admin_reject_subscription_pop'),
    path('manage/approvals/cash-subscription/<int:sub_id>/approve/', views.admin_approve_cash_subscription, name='admin_approve_cash_subscription'),
    path('manage/approvals/cash-order/<int:order_id>/decline/', views.admin_decline_cash_order, name='admin_decline_cash_order'),
    path('manage/approvals/company-cash-order/<int:order_id>/decline/', views.admin_decline_company_cash_order, name='admin_decline_company_cash_order'),
    path('manage/approvals/cash-subscription/<int:sub_id>/decline/', views.admin_decline_cash_subscription, name='admin_decline_cash_subscription'),
    # Subscriptions
    path('manage/subscriptions/', views.admin_subscriptions, name='admin_subscriptions'),
    path('manage/subscription/<int:sub_id>/', views.admin_update_subscription, name='admin_update_subscription'),
    # Plans
    path('manage/plans/', views.admin_plans, name='admin_plans'),
    path('manage/discount/', views.admin_update_discount, name='admin_update_discount'),
    # Users
    path('manage/users/', views.admin_users, name='admin_users'),
    path('manage/user/<int:user_id>/action/', views.admin_user_action, name='admin_user_action'),
    # Blog management
    path('manage/blog/', views.admin_blog_list, name='admin_blog_list'),
    path('manage/blog/new/', views.admin_blog_create, name='admin_blog_create'),
    path('manage/blog/<int:post_id>/', views.admin_blog_detail, name='admin_blog_detail'),
    path('manage/blog/<int:post_id>/edit/', views.admin_blog_edit, name='admin_blog_edit'),
    path('manage/blog/<int:post_id>/delete/', views.admin_blog_delete, name='admin_blog_delete'),
    path('manage/blog/<int:post_id>/toggle/', views.admin_blog_toggle, name='admin_blog_toggle'),
    path('manage/blog/comments/', views.admin_blog_comments, name='admin_blog_comments'),
    path('manage/blog/comment/<int:comment_id>/action/', views.admin_blog_comment_action, name='admin_blog_comment_action'),
    # Card pricing & images
    path('manage/card-pricing/', views.admin_card_pricing, name='admin_card_pricing'),
    path('manage/card-pricing/<int:product_id>/update/', views.admin_update_card_price, name='admin_update_card_price'),
    path('manage/card-pricing/<int:product_id>/upload-image/', views.admin_upload_card_image, name='admin_upload_card_image'),
    path('manage/card-image/<int:image_id>/delete/', views.admin_delete_card_image, name='admin_delete_card_image'),
    path('manage/card-image/<int:image_id>/set-primary/', views.admin_set_primary_card_image, name='admin_set_primary_card_image'),
    # NFC card URLs
    path('manage/nfc-urls/', views.admin_nfc_urls, name='admin_nfc_urls'),
    # Analytics
    path('manage/analytics/', views.admin_analytics, name='admin_analytics'),
    # Payment methods
    path('manage/payment-methods/', views.admin_payment_methods, name='admin_payment_methods'),
    path('manage/payment-methods/<int:method_id>/toggle/', views.admin_toggle_payment_method, name='admin_toggle_payment_method'),
    # Banking details
    path('manage/banking-details/', views.admin_banking_details, name='admin_banking_details'),
    path('manage/banking-details/<int:pk>/edit/', views.admin_edit_banking_detail, name='admin_edit_banking_detail'),
    path('manage/banking-details/<int:pk>/delete/', views.admin_delete_banking_detail, name='admin_delete_banking_detail'),
    # Video testimonials
    path('manage/testimonials/', views.admin_video_testimonials, name='admin_video_testimonials'),
    path('manage/testimonials/new/', views.admin_video_testimonial_create, name='admin_video_testimonial_create'),
    path('manage/testimonials/<int:pk>/edit/', views.admin_video_testimonial_edit, name='admin_video_testimonial_edit'),
    path('manage/testimonials/<int:pk>/delete/', views.admin_video_testimonial_delete, name='admin_video_testimonial_delete'),
    path('manage/testimonials/<int:pk>/toggle/', views.admin_video_testimonial_toggle, name='admin_video_testimonial_toggle'),
    # Partner logos
    path('manage/partner-logos/', views.admin_partner_logos, name='admin_partner_logos'),
    path('manage/partner-logos/new/', views.admin_partner_logo_create, name='admin_partner_logo_create'),
    path('manage/partner-logos/<int:pk>/edit/', views.admin_partner_logo_edit, name='admin_partner_logo_edit'),
    path('manage/partner-logos/<int:pk>/delete/', views.admin_partner_logo_delete, name='admin_partner_logo_delete'),
    path('manage/partner-logos/<int:pk>/toggle/', views.admin_partner_logo_toggle, name='admin_partner_logo_toggle'),
]
