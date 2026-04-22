"""
Regenerate QR codes for all profiles to fix domain issues.

Usage:
    python manage.py regenerate_qr_codes
    python manage.py regenerate_qr_codes --profile-id 123  # specific profile
"""

from django.core.management.base import BaseCommand
from profiles.models import Profile


class Command(BaseCommand):
    help = 'Regenerate QR codes for all profiles with the correct domain'

    def add_arguments(self, parser):
        parser.add_argument(
            '--profile-id',
            type=int,
            help='Regenerate QR for a specific profile ID only',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be regenerated without actually doing it',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        profile_id = options['profile_id']

        if profile_id:
            profiles = Profile.objects.filter(pk=profile_id)
        else:
            profiles = Profile.objects.all()

        total = profiles.count()
        self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Found {total} profile(s) to process\n")

        updated = 0
        for profile in profiles:
            old_url = profile.production_nfc_url
            
            if dry_run:
                self.stdout.write(f"  Would update: {profile.user.username} -> {old_url}")
                continue

            try:
                # Delete old QR code if exists
                if profile.qr_code:
                    profile.qr_code.delete(save=False)
                
                # Generate new QR code
                profile.generate_qr_code()
                updated += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Updated: {profile.user.username} -> {profile.production_nfc_url}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ Failed for {profile.user.username}: {e}"))

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"\nDone! Regenerated QR codes for {updated}/{total} profiles."))
        else:
            self.stdout.write(f"\nDry run complete. Use without --dry-run to actually regenerate.")
