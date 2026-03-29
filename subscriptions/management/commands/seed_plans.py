from django.core.management.base import BaseCommand
from subscriptions.models import Plan


class Command(BaseCommand):
    help = 'Seed MVP subscription plans'

    def handle(self, *args, **options):
        plans = [
            {
                'name': 'Starter',
                'slug': 'starter',
                'price': 3.00,
                'features': {'max_images': 5, 'analytics': False},
                'description': 'Perfect for getting started. Basic profile with essential features.',
                'badge_label': '',
                'is_highlighted': False,
            },
            {
                'name': 'Business',
                'slug': 'business',
                'price': 5.00,
                'features': {'max_images': 20, 'analytics': True},
                'description': 'Ideal for professionals. Tap analytics and more images.',
                'badge_label': 'Popular',
                'is_highlighted': True,
            },
            {
                'name': 'Pro',
                'slug': 'pro',
                'price': 10.00,
                'features': {'max_images': 50, 'analytics': True, 'custom_theme': True},
                'description': 'Everything you need. Custom themes, full analytics, max uploads.',
                'badge_label': 'Best Value',
                'is_highlighted': False,
            },
        ]
        for p in plans:
            Plan.objects.update_or_create(slug=p['slug'], defaults=p)
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(plans)} plans'))
