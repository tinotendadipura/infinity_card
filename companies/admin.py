from django.contrib import admin
from django.utils import timezone
from .models import Company, CompanyMembership, BulkCardOrder, ProofOfPayment, CardAssignment, CompanySubscription, CompanyBillingEvent


class CompanyMembershipInline(admin.TabularInline):
    model = CompanyMembership
    extra = 0
    fields = ('invite_email', 'employee_name', 'employee_title', 'role', 'user', 'is_active', 'joined_at')
    readonly_fields = ('invite_token', 'invited_at', 'joined_at')
    raw_id_fields = ('user',)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'member_count', 'email', 'created_by', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'slug', 'email')
    prepopulated_fields = {'slug': ('name',)}
    raw_id_fields = ('created_by',)
    inlines = [CompanyMembershipInline]


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ('employee_name', 'invite_email', 'company', 'role', 'is_active', 'user', 'joined_at')
    list_filter = ('role', 'is_active', 'company')
    search_fields = ('employee_name', 'invite_email', 'company__name', 'user__username')
    raw_id_fields = ('user', 'company')
    readonly_fields = ('invite_token', 'invited_at', 'joined_at')


@admin.register(BulkCardOrder)
class BulkCardOrderAdmin(admin.ModelAdmin):
    list_display = ('company', 'card_product', 'quantity', 'total_amount', 'status', 'design_option', 'paid_at', 'created_at')
    list_filter = ('status', 'design_option', 'card_product', 'payment_method')
    search_fields = ('company__name', 'paypal_order_id', 'shipping_contact_name')
    raw_id_fields = ('company', 'ordered_by')
    readonly_fields = ('paypal_order_id', 'created_at', 'paid_at', 'shipped_at', 'delivered_at')
    filter_horizontal = ('members',)

    fieldsets = (
        ('Order', {
            'fields': ('company', 'ordered_by', 'card_product', 'quantity', 'status'),
        }),
        ('Pricing & Payment', {
            'fields': ('unit_price', 'custom_design_fee', 'total_amount', 'payment_method', 'paypal_order_id', 'ecocash_phone'),
        }),
        ('Design', {
            'fields': ('design_option', 'design_front', 'design_back', 'design_notes'),
        }),
        ('Employees', {
            'fields': ('members',),
        }),
        ('Shipping', {
            'fields': ('shipping_company_name', 'shipping_contact_name', 'shipping_email', 'shipping_phone',
                       'shipping_address1', 'shipping_address2', 'shipping_city', 'shipping_state',
                       'shipping_zip', 'shipping_country'),
        }),
        ('Tracking & Delivery', {
            'fields': ('tracking_number', 'tracking_url', 'shipped_at', 'delivered_at'),
        }),
        ('Dates & Notes', {
            'fields': ('paid_at', 'created_at', 'notes'),
        }),
    )


@admin.register(ProofOfPayment)
class ProofOfPaymentAdmin(admin.ModelAdmin):
    list_display = ('pk', 'order', 'payment_type', 'amount_paid', 'reference_number', 'status', 'uploaded_by', 'created_at')
    list_filter = ('status', 'payment_type')
    search_fields = ('reference_number', 'order__company__name', 'uploaded_by__email')
    raw_id_fields = ('order', 'uploaded_by', 'reviewed_by')
    readonly_fields = ('created_at',)
    actions = ['approve_pop', 'reject_pop']

    fieldsets = (
        ('Payment Details', {
            'fields': ('order', 'uploaded_by', 'payment_type', 'status'),
        }),
        ('Proof', {
            'fields': ('document', 'reference_number', 'amount_paid', 'payment_date', 'notes'),
        }),
        ('Review', {
            'fields': ('reviewed_by', 'reviewed_at', 'rejection_reason'),
        }),
        ('Meta', {
            'fields': ('created_at',),
        }),
    )

    @admin.action(description='Approve selected proofs of payment')
    def approve_pop(self, request, queryset):
        for pop in queryset.filter(status='pending'):
            pop.status = 'approved'
            pop.reviewed_by = request.user
            pop.reviewed_at = timezone.now()
            pop.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

            order = pop.order
            if order.status == 'pending':
                order.status = 'paid'
                order.paid_at = timezone.now()
                order.save(update_fields=['status', 'paid_at'])

                # Create card assignments
                company = order.company
                session_members = order.members.all()
                if session_members.exists():
                    for m in session_members:
                        if not CardAssignment.objects.filter(company=company, bulk_order=order, membership=m).exists():
                            CardAssignment.objects.create(
                                company=company, membership=m, bulk_order=order,
                                card_product=order.card_product, status='assigned',
                                assigned_at=timezone.now(),
                            )
                    remaining = order.quantity - session_members.count()
                    for _ in range(max(0, remaining)):
                        CardAssignment.objects.create(
                            company=company, bulk_order=order,
                            card_product=order.card_product, status='unassigned',
                        )
                else:
                    for _ in range(order.quantity):
                        CardAssignment.objects.create(
                            company=company, bulk_order=order,
                            card_product=order.card_product, status='unassigned',
                        )

        self.message_user(request, f'{queryset.count()} proof(s) approved and orders activated.')

    @admin.action(description='Reject selected proofs of payment')
    def reject_pop(self, request, queryset):
        count = queryset.filter(status='pending').update(
            status='rejected',
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f'{count} proof(s) rejected.')


@admin.register(CompanySubscription)
class CompanySubscriptionAdmin(admin.ModelAdmin):
    list_display = ('company', 'plan', 'status', 'billing_period', 'num_cards', 'payment_method', 'started_at', 'expires_at')
    list_filter = ('status', 'billing_period', 'plan', 'payment_method')
    search_fields = ('company__name',)
    raw_id_fields = ('company', 'plan')
    readonly_fields = ('started_at',)
    actions = ['activate_subscriptions', 'suspend_subscriptions']

    def activate_subscriptions(self, request, queryset):
        count = queryset.update(status='active')
        self.message_user(request, f'{count} subscription(s) activated.')
    activate_subscriptions.short_description = 'Activate selected subscriptions'

    def suspend_subscriptions(self, request, queryset):
        count = queryset.update(status='suspended')
        self.message_user(request, f'{count} subscription(s) suspended.')
    suspend_subscriptions.short_description = 'Suspend selected subscriptions'


@admin.register(CompanyBillingEvent)
class CompanyBillingEventAdmin(admin.ModelAdmin):
    list_display = ('company', 'event_type', 'plan', 'amount', 'created_at')
    list_filter = ('event_type', 'plan')
    search_fields = ('company__name',)
    readonly_fields = ('company', 'event_type', 'plan', 'amount', 'note', 'created_at')


@admin.register(CardAssignment)
class CardAssignmentAdmin(admin.ModelAdmin):
    list_display = ('company', 'membership', 'card_product', 'status', 'assigned_at')
    list_filter = ('status', 'company')
    search_fields = ('company__name', 'membership__employee_name')
    raw_id_fields = ('company', 'membership', 'bulk_order')
