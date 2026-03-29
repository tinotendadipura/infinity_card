from django.core.management.base import BaseCommand

from profiles.models import Profile


class Command(BaseCommand):
    help = 'Generate QR codes for all profiles that do not have one yet.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Regenerate QR codes for all profiles, even if they already have one.',
        )

    def handle(self, *args, **options):
        force = options['force']
        if force:
            profiles = Profile.objects.select_related('user').all()
        else:
            profiles = Profile.objects.select_related('user').filter(qr_code='')

        total = profiles.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('All profiles already have QR codes.'))
            return

        self.stdout.write(f'Generating QR codes for {total} profile(s)...')

        for i, profile in enumerate(profiles, 1):
            profile.generate_qr_code()
            Profile.objects.filter(pk=profile.pk).update(qr_code=profile.qr_code.name)
            self.stdout.write(f'  [{i}/{total}] {profile.user.username} -> {profile.qr_code.name}')

        self.stdout.write(self.style.SUCCESS(f'Done. Generated {total} QR code(s).'))
