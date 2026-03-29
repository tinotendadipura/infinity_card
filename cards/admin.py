from django.contrib import admin
from django import forms
from .models import NFCCard, NFCCardProduct, CardOrder, PersonalProofOfPayment


class BulkImportForm(forms.Form):
    uids = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 10, 'placeholder': 'One UID per line'}),
        help_text='Enter one NFC card UID per line.',
    )


@admin.register(NFCCard)
class NFCCardAdmin(admin.ModelAdmin):
    list_display = ('uid', 'profile', 'is_active', 'assigned_at')
    list_filter = ('is_active',)
    search_fields = ('uid', 'profile__user__username')
    raw_id_fields = ('profile',)
    actions = ['activate_cards', 'deactivate_cards']
    change_list_template = 'admin/cards/nfccard/change_list.html'

    def activate_cards(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'{count} card(s) activated.')
    activate_cards.short_description = 'Activate selected cards'

    def deactivate_cards(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} card(s) deactivated.')
    deactivate_cards.short_description = 'Deactivate selected cards'

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('bulk-import/', self.admin_site.admin_view(self.bulk_import_view), name='cards_nfccard_bulk_import'),
        ]
        return custom_urls + urls

    def bulk_import_view(self, request):
        from django.shortcuts import redirect, render
        from django.contrib import messages

        if request.method == 'POST':
            form = BulkImportForm(request.POST)
            if form.is_valid():
                uids = [
                    line.strip()
                    for line in form.cleaned_data['uids'].splitlines()
                    if line.strip()
                ]
                created = 0
                for uid in uids:
                    _, was_created = NFCCard.objects.get_or_create(uid=uid)
                    if was_created:
                        created += 1
                messages.success(request, f'{created} new card(s) imported ({len(uids) - created} already existed).')
                return redirect('..')
        else:
            form = BulkImportForm()

        context = {
            **self.admin_site.each_context(request),
            'form': form,
            'title': 'Bulk Import NFC Card UIDs',
            'opts': self.model._meta,
        }
        return render(request, 'admin/cards/nfccard/bulk_import.html', context)


@admin.register(NFCCardProduct)
class NFCCardProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'material', 'price', 'custom_price', 'is_available', 'sort_order')
    list_filter = ('is_available', 'material')
    list_editable = ('price', 'custom_price', 'is_available', 'sort_order')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(CardOrder)
class CardOrderAdmin(admin.ModelAdmin):
    list_display = ('user', 'card_product', 'amount', 'status', 'payment_method', 'design_option', 'channel', 'shipping_city_country', 'subscription_activated', 'paid_at', 'created_at')
    list_filter = ('status', 'payment_method', 'channel', 'subscription_activated', 'card_product', 'design_option')
    search_fields = ('user__username', 'user__email', 'paypal_order_id', 'ecocash_phone', 'shipping_first_name', 'shipping_last_name', 'tracking_number')
    raw_id_fields = ('user',)
    readonly_fields = ('paypal_order_id', 'created_at', 'paid_at', 'shipped_at', 'delivered_at', 'custom_design_fee')
    actions = ['mark_paid', 'mark_shipped', 'mark_delivered', 'activate_subscription']

    fieldsets = (
        ('Order', {
            'fields': ('user', 'card_product', 'amount', 'status', 'payment_method', 'channel', 'paypal_order_id', 'ecocash_phone', 'subscription_activated'),
        }),
        ('Card Design', {
            'fields': ('design_option', 'custom_design_fee', 'design_front', 'design_back', 'design_notes'),
        }),
        ('Contact', {
            'fields': ('shipping_first_name', 'shipping_last_name', 'shipping_email', 'shipping_phone'),
        }),
        ('Shipping Address', {
            'fields': ('shipping_address1', 'shipping_address2', 'shipping_city', 'shipping_state', 'shipping_zip', 'shipping_country'),
        }),
        ('Tracking & Delivery', {
            'fields': ('tracking_number', 'tracking_url', 'shipped_at', 'delivered_at'),
        }),
        ('Dates & Notes', {
            'fields': ('paid_at', 'created_at', 'notes'),
        }),
    )

    def shipping_city_country(self, obj):
        parts = [p for p in [obj.shipping_city, obj.shipping_country] if p]
        return ', '.join(parts) or '—'
    shipping_city_country.short_description = 'Ship To'

    def mark_paid(self, request, queryset):
        """Admin action: mark orders as paid (does NOT activate subscription)."""
        from django.utils import timezone as tz
        count = 0
        for order in queryset.filter(status='pending'):
            order.status = 'paid'
            order.paid_at = tz.now()
            order.save()
            count += 1
        self.message_user(request, f'{count} order(s) marked as paid.')
    mark_paid.short_description = 'Mark as Paid'

    def mark_shipped(self, request, queryset):
        from django.utils import timezone as tz
        count = 0
        for order in queryset.filter(status='paid'):
            order.status = 'shipped'
            order.shipped_at = tz.now()
            order.save()
            count += 1
        self.message_user(request, f'{count} order(s) marked as shipped.')
    mark_shipped.short_description = 'Mark as Shipped'

    def mark_delivered(self, request, queryset):
        from django.utils import timezone as tz
        count = 0
        for order in queryset.filter(status='shipped'):
            order.status = 'delivered'
            order.delivered_at = tz.now()
            order.save()
            count += 1
        self.message_user(request, f'{count} order(s) marked as delivered.')
    mark_delivered.short_description = 'Mark as Delivered'

    def activate_subscription(self, request, queryset):
        """Admin action: activate monthly subscription for selected paid orders."""
        from cards.views import _activate_subscription_after_purchase
        count = 0
        for order in queryset.exclude(status__in=['pending', 'cancelled']).filter(subscription_activated=False):
            _activate_subscription_after_purchase(order.user, order)
            count += 1
        self.message_user(request, f'{count} subscription(s) activated.')
    activate_subscription.short_description = 'Activate Subscription (start monthly billing)'


class PersonalProofOfPaymentInline(admin.TabularInline):
    model = PersonalProofOfPayment
    extra = 0
    readonly_fields = ('uploaded_by', 'payment_type', 'document', 'reference_number', 'amount_paid', 'payment_date', 'created_at')


@admin.register(PersonalProofOfPayment)
class PersonalProofOfPaymentAdmin(admin.ModelAdmin):
    list_display = ('order', 'payment_type', 'status', 'amount_paid', 'reference_number', 'uploaded_by', 'created_at')
    list_filter = ('status', 'payment_type')
    search_fields = ('order__user__username', 'reference_number')
    raw_id_fields = ('order', 'uploaded_by', 'reviewed_by')
    readonly_fields = ('created_at',)
    actions = ['approve_pop', 'reject_pop']

    def approve_pop(self, request, queryset):
        from django.utils import timezone as tz
        count = 0
        for pop in queryset.filter(status='pending'):
            pop.status = 'approved'
            pop.reviewed_by = request.user
            pop.reviewed_at = tz.now()
            pop.save()
            # Mark the order as paid
            order = pop.order
            if order.status == 'pending':
                order.status = 'paid'
                order.paid_at = tz.now()
                order.save(update_fields=['status', 'paid_at'])
            count += 1
        self.message_user(request, f'{count} proof(s) of payment approved and order(s) marked as paid.')
    approve_pop.short_description = 'Approve POP & mark order as Paid'

    def reject_pop(self, request, queryset):
        count = queryset.filter(status='pending').update(status='rejected')
        self.message_user(request, f'{count} proof(s) of payment rejected.')
    reject_pop.short_description = 'Reject POP'
