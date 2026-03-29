from django.core.management.base import BaseCommand
from themes.models import Theme


class Command(BaseCommand):
    help = 'Seed default themes'

    def handle(self, *args, **options):
        themes = [
            {
                'name': 'InfinityCard Classic',
                'primary_color': '#2EC4B6',
                'secondary_color': '#6B2FA0',
                'background_color': '#FFFFFF',
                'text_color': '#1E293B',
                'is_default': True,
            },
            {
                'name': 'Deep Purple',
                'primary_color': '#6B2FA0',
                'secondary_color': '#2EC4B6',
                'background_color': '#F5F3FF',
                'text_color': '#1E1B4B',
            },
            {
                'name': 'Midnight',
                'primary_color': '#8B5CF6',
                'secondary_color': '#2EC4B6',
                'background_color': '#0F172A',
                'text_color': '#E2E8F0',
            },
            {
                'name': 'Forest',
                'primary_color': '#10B981',
                'secondary_color': '#6B2FA0',
                'background_color': '#F0FDF4',
                'text_color': '#14532D',
            },
            {
                'name': 'Coral Sunset',
                'primary_color': '#F97316',
                'secondary_color': '#6B2FA0',
                'background_color': '#FFF7ED',
                'text_color': '#431407',
            },
        ]
        for t in themes:
            Theme.objects.update_or_create(name=t['name'], defaults=t)
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(themes)} themes'))
