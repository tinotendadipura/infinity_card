from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile_on_signup(sender, instance, created, **kwargs):
    if created:
        from profiles.models import Profile

        # Build display name from first/last name, fallback to username
        full_name = f'{instance.first_name} {instance.last_name}'.strip()
        if not full_name:
            full_name = instance.username.replace('-', ' ').title()

        # Create profile without category — category is chosen during onboarding
        Profile.objects.create(
            user=instance,
            category=None,
            display_name=full_name,
        )

        # No subscription is created on signup.
        # Subscription is only activated after the user purchases an NFC card
        # and the card is marked as delivered by an admin.
