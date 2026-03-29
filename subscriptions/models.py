from django.conf import settings
from django.db import models
from django.utils import timezone


class Plan(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    features = models.JSONField(default=dict)
    subtitle = models.CharField(max_length=100, blank=True, help_text='e.g., "For individuals", "For growing teams"')
    description = models.TextField(blank=True, help_text='Short marketing description')
    badge_label = models.CharField(max_length=20, blank=True, help_text='e.g., "Popular", "Best Value"')
    is_highlighted = models.BooleanField(default=False, help_text='Visually emphasize on pricing page')
    display_features = models.JSONField(
        default=list, blank=True,
        help_text='List of {"text": "...", "included": true/false} for homepage pricing display',
    )
    yearly_discount_percent = models.PositiveIntegerField(
        default=20, help_text='Discount percentage for yearly billing (e.g. 20 = 20% off)',
    )
    paypal_product_id = models.CharField(max_length=100, blank=True, help_text='PayPal Catalog Product ID')
    paypal_plan_id = models.CharField(max_length=100, blank=True, help_text='PayPal Monthly Billing Plan ID')
    paypal_yearly_plan_id = models.CharField(max_length=100, blank=True, help_text='PayPal Yearly Billing Plan ID')

    @property
    def yearly_price(self):
        """Monthly price after yearly discount, times 12."""
        from decimal import Decimal
        discount = Decimal(self.yearly_discount_percent) / Decimal(100)
        monthly_discounted = self.price * (Decimal(1) - discount)
        return (monthly_discounted * 12).quantize(Decimal('0.01'))

    @property
    def yearly_monthly_price(self):
        """Effective per-month price when billed yearly."""
        from decimal import Decimal
        discount = Decimal(self.yearly_discount_percent) / Decimal(100)
        return (self.price * (Decimal(1) - discount)).quantize(Decimal('0.01'))

    def __str__(self):
        return f'{self.name} (${self.price}/mo)'

    class Meta:
        ordering = ['price']


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
    ]

    PERIOD_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
        ('ecocash', 'EcoCash'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    billing_period = models.CharField(
        max_length=10, choices=PERIOD_CHOICES, default='monthly',
        help_text='Monthly or yearly billing cycle',
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='paypal')
    ecocash_phone = models.CharField(max_length=20, blank=True, help_text='EcoCash phone used for subscription payment')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    paypal_subscription_id = models.CharField(
        max_length=100, blank=True, db_index=True,
        help_text='PayPal Subscription ID (e.g. I-XXXXXXXX)',
    )
    pending_plan = models.ForeignKey(
        Plan, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pending_subscriptions',
        help_text='Plan the user will switch to at end of current billing period (scheduled downgrade)',
    )
    pending_period = models.CharField(
        max_length=10, choices=PERIOD_CHOICES, blank=True,
        help_text='Billing period for the pending plan change',
    )

    def is_active(self):
        return self.status in ('active', 'cancelled') and self.expires_at > timezone.now()

    def days_remaining(self):
        if self.status in ('active', 'cancelled') and self.expires_at > timezone.now():
            return (self.expires_at - timezone.now()).days
        return 0

    def __str__(self):
        return f'{self.user.username} – {self.plan.name} ({self.status})'


class BillingEvent(models.Model):
    EVENT_TYPES = [
        ('subscribe', 'New Subscription'),
        ('upgrade', 'Plan Upgrade'),
        ('downgrade', 'Plan Downgrade'),
        ('renew', 'Renewal'),
        ('cancel', 'Cancellation'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='billing_events',
    )
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} – {self.get_event_type_display()} – ${self.amount}'


class SubscriptionProofOfPayment(models.Model):
    """Proof of payment uploaded by a user for bank transfer / EcoCash subscription payments."""
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    PAYMENT_TYPE_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('ecocash', 'EcoCash'),
    ]

    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='proof_of_payments')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    document = models.ImageField(upload_to='proof_of_payment/subscriptions/%Y/%m/', help_text='Screenshot or photo of payment confirmation')
    reference_number = models.CharField(max_length=100, blank=True, help_text='Bank reference or EcoCash transaction ID')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, help_text='Amount transferred')
    payment_date = models.DateField(help_text='Date the payment was made')
    notes = models.TextField(blank=True, help_text='Additional details about the payment')

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='subscription_pop_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Sub POP #{self.pk} — {self.get_payment_type_display()} — {self.get_status_display()}'


class Payment(models.Model):
    """Tracks individual PayPal payment transactions."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    subscription = models.ForeignKey(
        Subscription, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payments',
    )
    paypal_payment_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    status = models.CharField(max_length=30, default='COMPLETED')
    paid_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    raw_data = models.JSONField(default=dict, blank=True, help_text='Raw PayPal webhook payload')

    class Meta:
        ordering = ['-paid_at']

    def __str__(self):
        return f'{self.user.username} – ${self.amount} – {self.paypal_payment_id}'


class PaymentMethodSettings(models.Model):
    """Global settings for enabling/disabling payment methods."""
    PAYMENT_METHOD_CHOICES = [
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
        ('ecocash', 'EcoCash'),
        ('cash', 'Cash Payment'),
    ]
    
    method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, unique=True)
    is_enabled = models.BooleanField(default=True)
    display_name = models.CharField(max_length=50)
    description = models.TextField(blank=True, help_text='Internal notes about this payment method')
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Payment Method Setting'
        verbose_name_plural = 'Payment Method Settings'
        ordering = ['method']
    
    def __str__(self):
        status = 'Enabled' if self.is_enabled else 'Disabled'
        return f'{self.display_name} ({status})'
    
    @classmethod
    def is_method_enabled(cls, method):
        """Check if a payment method is enabled. Returns True if not found (default enabled)."""
        try:
            setting = cls.objects.get(method=method)
            return setting.is_enabled
        except cls.DoesNotExist:
            return True  # Default to enabled if not configured
    
    @classmethod
    def get_enabled_methods(cls):
        """Get list of enabled payment method codes."""
        enabled = []
        for method_code, _ in cls.PAYMENT_METHOD_CHOICES:
            if cls.is_method_enabled(method_code):
                enabled.append(method_code)
        return enabled


class BankingDetail(models.Model):
    """Platform banking details shown to customers for bank transfer payments.
    Admins can add multiple bank accounts and mark one as primary."""
    bank_name = models.CharField(max_length=100)
    account_name = models.CharField(max_length=150)
    account_number = models.CharField(max_length=50)
    branch = models.CharField(max_length=150, blank=True)
    branch_code = models.CharField(max_length=20, blank=True)
    swift_code = models.CharField(max_length=20, blank=True)
    currency = models.CharField(max_length=10, default='USD')
    is_active = models.BooleanField(default=True, help_text='Show this account to customers')
    is_primary = models.BooleanField(default=False, help_text='Primary account shown first')
    notes = models.TextField(blank=True, help_text='Internal admin notes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Banking Detail'
        verbose_name_plural = 'Banking Details'
        ordering = ['-is_primary', 'bank_name']

    def __str__(self):
        return f'{self.bank_name} – {self.account_number}'

    def save(self, *args, **kwargs):
        # If this is set as primary, unset all others
        if self.is_primary:
            BankingDetail.objects.filter(is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Return active banking details, primary first."""
        return cls.objects.filter(is_active=True)

    @classmethod
    def get_primary(cls):
        """Return the primary bank account, or the first active one."""
        return cls.objects.filter(is_active=True).first()

    def as_dict(self):
        """Return a dict matching the old settings.BANK_DETAILS format."""
        return {
            'bank_name': self.bank_name,
            'account_name': self.account_name,
            'account_number': self.account_number,
            'branch': self.branch,
            'branch_code': self.branch_code,
            'swift_code': self.swift_code,
            'currency': self.currency,
        }
