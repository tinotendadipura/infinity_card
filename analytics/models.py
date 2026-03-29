from django.db import models


class TapEvent(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile',
        on_delete=models.CASCADE,
        related_name='tap_events',
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['profile', '-timestamp']),
        ]

    def __str__(self):
        return f'Tap on {self.profile} at {self.timestamp}'


class ProfileEvent(models.Model):
    EVENT_TYPES = [
        ('profile_view', 'Profile View'),
        ('catalog_view', 'Catalog Page View'),
        ('product_click', 'Product Click'),
        ('catalog_seeall', 'Catalog See All Click'),
        ('contact_click', 'Contact Click'),
        ('social_click', 'Social Link Click'),
        ('website_click', 'Website Click'),
    ]

    profile = models.ForeignKey(
        'profiles.Profile',
        on_delete=models.CASCADE,
        related_name='profile_events',
    )
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    item_id = models.PositiveIntegerField(null=True, blank=True, help_text='Related catalog item ID')
    item_title = models.CharField(max_length=200, blank=True, help_text='Snapshot of item title at event time')
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['profile', 'event_type', '-timestamp']),
            models.Index(fields=['profile', '-timestamp']),
        ]

    def __str__(self):
        return f'{self.get_event_type_display()} on {self.profile} at {self.timestamp}'
