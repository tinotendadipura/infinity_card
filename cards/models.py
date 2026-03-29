from django.conf import settings
from django.db import models


class NFCCardProduct(models.Model):
    """A type of physical NFC business card available for purchase."""
    MATERIAL_CHOICES = [
        ('plastic', 'Plastic'),
        ('plastic_gold', 'Plastic Gold'),
        ('plastic_transparent', 'Plastic Transparent'),
        ('wood', 'Wood'),
        ('metal', 'Metal'),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    material = models.CharField(max_length=30, choices=MATERIAL_CHOICES, unique=True)
    price = models.DecimalField(max_digits=6, decimal_places=2, help_text='Standard InfinityCard price in USD')
    custom_price = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text='Custom branded card price in USD (0 = not available)')
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='card_products/', blank=True)
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'price']

    def __str__(self):
        return f'{self.name} (${self.price})'


class CardProductImage(models.Model):
    """Gallery image for an NFC card product."""
    product = models.ForeignKey(NFCCardProduct, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to='card_products/gallery/')
    caption = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False, help_text='Primary image shown as the main product photo')
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'sort_order', '-created_at']

    def __str__(self):
        return f'{self.product.name} — Image #{self.pk}'

    def save(self, *args, **kwargs):
        if self.is_primary:
            CardProductImage.objects.filter(product=self.product, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class CardOrder(models.Model):
    """Tracks a one-time NFC card purchase."""
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    CHANNEL_CHOICES = [
        ('online', 'Online (PayPal)'),
        ('physical', 'Physical / In-Person'),
        ('admin', 'Admin Manual'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('paypal', 'PayPal'),
        ('bank_transfer', 'Bank Transfer'),
        ('ecocash', 'EcoCash'),
        ('cash', 'Cash Payment'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='card_orders',
    )
    card_product = models.ForeignKey(NFCCardProduct, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='online')
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='paypal')
    paypal_order_id = models.CharField(max_length=100, blank=True, db_index=True)
    ecocash_phone = models.CharField(max_length=20, blank=True, help_text='EcoCash phone number used for payment')
    subscription_activated = models.BooleanField(default=False, help_text='Whether monthly subscription was activated after purchase')

    # Shipping address (structured, Shopify-style)
    shipping_first_name = models.CharField(max_length=100, blank=True)
    shipping_last_name = models.CharField(max_length=100, blank=True)
    shipping_email = models.EmailField(blank=True)
    shipping_phone = models.CharField(max_length=30, blank=True)
    shipping_address1 = models.CharField('Address line 1', max_length=255, blank=True)
    shipping_address2 = models.CharField('Address line 2 (apt, suite, etc.)', max_length=255, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField('State / Province', max_length=100, blank=True)
    shipping_zip = models.CharField('ZIP / Postal code', max_length=20, blank=True)
    shipping_country = models.CharField(max_length=100, default='United States', blank=True)

    # Card design
    DESIGN_CHOICES = [
        ('standard', 'InfinityCard Branded'),
        ('custom', 'Custom Branded'),
    ]
    design_option = models.CharField(max_length=10, choices=DESIGN_CHOICES, default='standard')
    design_front = models.ImageField(upload_to='card_designs/', blank=True, help_text='Front design uploaded by user')
    design_back = models.ImageField(upload_to='card_designs/', blank=True, help_text='Back design uploaded by user')
    design_notes = models.TextField(blank=True, help_text='Instructions for custom design (name, title, colors, etc.)')
    custom_design_fee = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text='Extra charge for custom design')

    tracking_number = models.CharField(max_length=200, blank=True, help_text='Shipping tracking number')
    tracking_url = models.URLField(blank=True, help_text='Tracking URL for the shipment')
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True, help_text='Reason for declining a cash payment')
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} - {self.card_product.name} ({self.get_status_display()})'


class NFCCard(models.Model):
    uid = models.CharField(max_length=64, unique=True, db_index=True)
    profile = models.ForeignKey(
        'profiles.Profile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='nfc_cards',
    )
    is_active = models.BooleanField(default=False)
    assigned_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Card {self.uid} → {self.profile or "Unassigned"}'


class PersonalProofOfPayment(models.Model):
    """Proof of payment uploaded by a personal user for bank transfer / EcoCash card orders."""
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    PAYMENT_TYPE_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('ecocash', 'EcoCash'),
    ]

    order = models.ForeignKey(CardOrder, on_delete=models.CASCADE, related_name='proof_of_payments')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    document = models.ImageField(upload_to='proof_of_payment/personal/%Y/%m/', help_text='Screenshot or photo of payment confirmation')
    reference_number = models.CharField(max_length=100, blank=True, help_text='Bank reference or EcoCash transaction ID')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, help_text='Amount transferred')
    payment_date = models.DateField(help_text='Date the payment was made')
    notes = models.TextField(blank=True, help_text='Additional details about the payment')

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='personal_pop_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'POP #{self.pk} — {self.get_payment_type_display()} — {self.get_status_display()}'
