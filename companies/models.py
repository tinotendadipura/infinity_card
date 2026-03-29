import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Company(models.Model):
    """An organization that manages NFC cards for its employees."""
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, help_text='URL-friendly company identifier')
    logo = models.ImageField(upload_to='company_logos/', blank=True)
    profile_picture = models.ImageField(upload_to='company_profiles/', blank=True)
    website = models.URLField(blank=True)
    industry = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True, help_text='Company billing/physical address')
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True, help_text='Company contact email')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='companies_created',
        help_text='The user who registered this company',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'companies'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        return self.memberships.filter(is_active=True).count()

    @property
    def admin_members(self):
        return self.memberships.filter(role='admin', is_active=True)


class CompanyMembership(models.Model):
    """Links a user to a company with a role."""
    ROLE_CHOICES = [
        ('admin', 'Company Admin'),
        ('employee', 'Employee'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_memberships',
        null=True,
        blank=True,
        help_text='Set once the user accepts the invite or is created',
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='employee')
    is_active = models.BooleanField(default=True)

    # Invite fields
    invite_email = models.EmailField(help_text='Email the invite was sent to')
    invite_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_at = models.DateTimeField(auto_now_add=True)
    joined_at = models.DateTimeField(null=True, blank=True)

    # Employee info (for card ordering before they join)
    employee_name = models.CharField(max_length=200, blank=True, help_text='Full name for the card')
    employee_title = models.CharField(max_length=200, blank=True, help_text='Job title for the card')

    class Meta:
        unique_together = [('company', 'invite_email')]
        ordering = ['company', 'role', 'employee_name']

    def __str__(self):
        name = self.employee_name or self.invite_email
        return f'{name} @ {self.company.name} ({self.get_role_display()})'

    @property
    def is_pending(self):
        return self.user is None and self.is_active

    def accept(self, user):
        """Accept the invite and link the user."""
        self.user = user
        self.joined_at = timezone.now()
        self.save(update_fields=['user', 'joined_at'])


class BulkCardOrder(models.Model):
    """A bulk card order placed by a company for its employees."""
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    DESIGN_CHOICES = [
        ('standard', 'InfinityCard Branded'),
        ('custom', 'Custom Branded'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='bulk_orders')
    ordered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='bulk_orders_placed',
    )
    card_product = models.ForeignKey(
        'cards.NFCCardProduct',
        on_delete=models.PROTECT,
        related_name='bulk_orders',
    )
    quantity = models.PositiveIntegerField(help_text='Number of cards to order')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Pricing
    unit_price = models.DecimalField(max_digits=6, decimal_places=2)
    custom_design_fee = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Design
    design_option = models.CharField(max_length=10, choices=DESIGN_CHOICES, default='standard')
    design_front = models.ImageField(upload_to='company_designs/', blank=True)
    design_back = models.ImageField(upload_to='company_designs/', blank=True)
    design_notes = models.TextField(blank=True)

    # Shipping
    shipping_company_name = models.CharField(max_length=200, blank=True)
    shipping_contact_name = models.CharField(max_length=200, blank=True)
    shipping_email = models.EmailField(blank=True)
    shipping_phone = models.CharField(max_length=30, blank=True)
    shipping_address1 = models.CharField(max_length=255, blank=True)
    shipping_address2 = models.CharField(max_length=255, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField(max_length=100, blank=True)
    shipping_zip = models.CharField(max_length=20, blank=True)
    shipping_country = models.CharField(max_length=100, default='United States', blank=True)

    # Tracking
    tracking_number = models.CharField(max_length=200, blank=True)
    tracking_url = models.URLField(blank=True)

    # Payment
    PAYMENT_METHOD_CHOICES = [
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
        ('ecocash', 'EcoCash'),
        ('cash', 'Cash Payment'),
    ]
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='paypal')
    paypal_order_id = models.CharField(max_length=100, blank=True, db_index=True)
    ecocash_phone = models.CharField(max_length=20, blank=True, help_text='EcoCash phone number used for payment')

    # Dates
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True, help_text='Reason for declining a cash payment')
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Link to employees this order covers
    members = models.ManyToManyField(
        CompanyMembership,
        blank=True,
        related_name='bulk_orders',
        help_text='Employees included in this order',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.company.name} — {self.quantity}x {self.card_product.name} ({self.get_status_display()})'


class CompanySubscription(models.Model):
    """A subscription plan for a company (mirrors personal Subscription but linked to Company)."""
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

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey('subscriptions.Plan', on_delete=models.PROTECT, related_name='company_subscriptions')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    billing_period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default='monthly')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='paypal')
    num_cards = models.PositiveIntegerField(default=1, help_text='Number of NFC cards billed for')
    ecocash_phone = models.CharField(max_length=20, blank=True, help_text='EcoCash phone used for subscription payment')
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    paypal_subscription_id = models.CharField(
        max_length=100, blank=True, db_index=True,
        help_text='PayPal Subscription ID (e.g. I-XXXXXXXX)',
    )

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.company.name} – {self.plan.name} ({self.status})'

    def is_active(self):
        return self.status in ('active', 'cancelled') and self.expires_at > timezone.now()

    def days_remaining(self):
        if self.status in ('active', 'cancelled') and self.expires_at > timezone.now():
            return (self.expires_at - timezone.now()).days
        return 0


class CompanyBillingEvent(models.Model):
    """Tracks billing events for a company subscription."""
    EVENT_TYPES = [
        ('subscribe', 'New Subscription'),
        ('upgrade', 'Plan Upgrade'),
        ('downgrade', 'Plan Downgrade'),
        ('renew', 'Renewal'),
        ('cancel', 'Cancellation'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='billing_events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    plan = models.ForeignKey('subscriptions.Plan', on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.company.name} – {self.get_event_type_display()} – ${self.amount}'


class ProofOfPayment(models.Model):
    """Stores proof-of-payment uploads for bank transfer and EcoCash payments."""
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    PAYMENT_TYPE_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('ecocash', 'EcoCash'),
    ]

    order = models.ForeignKey(BulkCardOrder, on_delete=models.CASCADE, related_name='proof_of_payments')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    # Upload
    document = models.ImageField(upload_to='proof_of_payment/%Y/%m/', help_text='Screenshot or photo of payment confirmation')
    reference_number = models.CharField(max_length=100, blank=True, help_text='Bank reference or EcoCash transaction ID')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, help_text='Amount transferred')
    payment_date = models.DateField(help_text='Date the payment was made')
    notes = models.TextField(blank=True, help_text='Additional details about the payment')

    # Review
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pop_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'POP #{self.pk} — {self.get_payment_type_display()} — {self.get_status_display()}'


class CardAssignment(models.Model):
    """Tracks which NFC card is assigned to which employee."""
    STATUS_CHOICES = [
        ('unassigned', 'Unassigned'),
        ('assigned', 'Assigned'),
        ('active', 'Active'),
        ('deactivated', 'Deactivated'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='card_assignments')
    membership = models.ForeignKey(
        CompanyMembership, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='card_assignments',
    )
    bulk_order = models.ForeignKey(
        BulkCardOrder, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='card_assignments',
    )
    card_product = models.ForeignKey(
        'cards.NFCCardProduct', on_delete=models.PROTECT,
        related_name='company_assignments',
    )
    nfc_card = models.ForeignKey(
        'cards.NFCCard', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='company_assignment',
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='unassigned')
    assigned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        employee = self.membership.employee_name if self.membership else 'Unassigned'
        return f'{self.card_product.name} → {employee} ({self.get_status_display()})'
