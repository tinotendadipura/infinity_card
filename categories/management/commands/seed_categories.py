from django.core.management.base import BaseCommand
from categories.models import Category


class Command(BaseCommand):
    help = 'Seed MVP categories'

    def handle(self, *args, **options):
        categories = [
            {
                'name': 'Business / Entrepreneur',
                'slug': 'business',
                'description': 'For business owners and entrepreneurs.',
                'fields_config': {
                    'sections': ['bio', 'services', 'contact', 'social_links', 'cta'],
                    'cta_label': 'Get in Touch',
                },
            },
            {
                'name': 'Freelancer / Consultant',
                'slug': 'freelancer',
                'description': 'For freelancers, consultants, and independent professionals.',
                'fields_config': {
                    'sections': ['bio', 'skills', 'portfolio', 'contact', 'social_links', 'cta'],
                    'cta_label': 'Hire Me',
                },
            },
            {
                'name': 'Real Estate Agent',
                'slug': 'real_estate',
                'description': 'For real estate agents and property managers.',
                'fields_config': {
                    'sections': ['bio', 'listings', 'contact', 'social_links', 'cta'],
                    'cta_label': 'View Listings',
                },
            },
            {
                'name': 'Restaurant / Food Business',
                'slug': 'restaurant',
                'description': 'For restaurants, cafes, and food businesses.',
                'fields_config': {
                    'sections': ['bio', 'menu', 'hours', 'location', 'contact', 'cta'],
                    'cta_label': 'Order Now',
                },
            },
            {
                'name': 'Creative (Photo/Video)',
                'slug': 'creative',
                'description': 'For photographers, videographers, and visual creatives.',
                'fields_config': {
                    'sections': ['bio', 'gallery', 'services', 'contact', 'social_links', 'cta'],
                    'cta_label': 'Book a Session',
                },
            },
            {
                'name': 'Events (Catering/Decor)',
                'slug': 'events',
                'description': 'For event planners, caterers, and decor specialists.',
                'fields_config': {
                    'sections': ['bio', 'packages', 'gallery', 'contact', 'social_links', 'cta'],
                    'cta_label': 'Get a Quote',
                },
            },
            {
                'name': 'General Personal Profile',
                'slug': 'personal',
                'description': 'A general-purpose personal profile.',
                'fields_config': {
                    'sections': ['bio', 'contact', 'social_links'],
                    'cta_label': 'Connect',
                },
            },
        ]
        for c in categories:
            Category.objects.update_or_create(slug=c['slug'], defaults=c)
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(categories)} categories'))
