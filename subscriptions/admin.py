from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from .models import Plan, Subscription, BillingEvent, Payment


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'price', 'yearly_discount_percent', 'paypal_plan_id', 'paypal_yearly_plan_id')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('paypal_product_id', 'paypal_plan_id', 'paypal_yearly_plan_id')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'billing_period', 'is_currently_active', 'started_at', 'expires_at', 'paypal_subscription_id')
    list_filter = ('status', 'plan')
    search_fields = ('user__username', 'paypal_subscription_id')
    raw_id_fields = ('user',)
    actions = ['extend_30_days', 'suspend_subscriptions', 'reactivate_subscriptions']

    @admin.display(boolean=True, description='Currently Active')
    def is_currently_active(self, obj):
        return obj.is_active()

    def extend_30_days(self, request, queryset):
        for sub in queryset:
            sub.expires_at = max(sub.expires_at, timezone.now()) + timedelta(days=30)
            sub.status = 'active'
            sub.save()
        self.message_user(request, f'{queryset.count()} subscription(s) extended by 30 days.')
    extend_30_days.short_description = 'Extend by 30 days & activate'

    def suspend_subscriptions(self, request, queryset):
        count = queryset.update(status='suspended')
        self.message_user(request, f'{count} subscription(s) suspended.')
    suspend_subscriptions.short_description = 'Suspend selected subscriptions'

    def reactivate_subscriptions(self, request, queryset):
        for sub in queryset:
            if sub.expires_at < timezone.now():
                sub.expires_at = timezone.now() + timedelta(days=30)
            sub.status = 'active'
            sub.save()
        self.message_user(request, f'{queryset.count()} subscription(s) reactivated.')
    reactivate_subscriptions.short_description = 'Reactivate selected subscriptions'


@admin.register(BillingEvent)
class BillingEventAdmin(admin.ModelAdmin):
    list_display = ('user', 'event_type', 'plan', 'amount', 'created_at')
    list_filter = ('event_type', 'plan')
    search_fields = ('user__username',)
    readonly_fields = ('user', 'event_type', 'plan', 'amount', 'note', 'created_at')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('user', 'paypal_payment_id', 'amount', 'currency', 'status', 'paid_at')
    list_filter = ('status', 'currency')
    search_fields = ('user__username', 'paypal_payment_id')
    readonly_fields = ('user', 'subscription', 'paypal_payment_id', 'amount', 'currency', 'status', 'paid_at', 'raw_data')
