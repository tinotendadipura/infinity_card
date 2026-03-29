from django.urls import path
from . import views

app_name = 'cards'

urlpatterns = [
    # Main shop views
    path('shop/', views.card_shop, name='shop'),
    path('store/', views.ecommerce_store, name='ecommerce_store'),
    
    # Purchase flow
    path('shop/buy/<slug:slug>/', views.buy_card, name='buy_card'),
    path('shop/return/', views.purchase_return, name='purchase_return'),
    path('shop/cancel/', views.purchase_cancel, name='purchase_cancel'),
    path('orders/<int:pk>/upload-pop/', views.upload_pop, name='upload_pop'),
    path('tap/<str:card_uid>/', views.tap_redirect, name='tap'),

    # Shopping cart (AJAX)
    path('cart/', views.cart_data, name='cart_data'),
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/', views.update_cart, name='update_cart'),
    path('cart/remove/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/clear/', views.clear_cart, name='clear_cart'),
]
