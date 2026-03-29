"""
Management command to process subscription lifecycle events.

This is a standalone fallback that does NOT require Celery or Redis.
Run it via cron or Windows Task Scheduler in environments where
Celery is unavailable.

Usage:
  # Run all subscription processing tasks:
  python manage.py process_subscriptions

  # Run only specific tasks:
  python manage.py process_subscriptions --downgrades
  python manage.py process_subscriptions --expire
  python manage.py process_subscriptions --reminders

  # Cron example (run every hour):
  0 * * * * cd /path/to/project && python manage.py process_subscriptions
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Process subscription lifecycle: apply pending downgrades, expire old subscriptions, send reminders.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--downgrades', action='store_true',
            help='Only apply pending downgrades',
        )
        parser.add_argument(
            '--expire', action='store_true',
            help='Only expire overdue subscriptions',
        )
        parser.add_argument(
            '--reminders', action='store_true',
            help='Only send expiry reminders',
        )

    def handle(self, *args, **options):
        from subscriptions.tasks import (
            apply_pending_downgrades,
            expire_subscriptions,
            send_expiry_reminders,
        )

        run_all = not any([options['downgrades'], options['expire'], options['reminders']])

        if run_all or options['downgrades']:
            self.stdout.write(self.style.NOTICE('Applying pending downgrades...'))
            result = apply_pending_downgrades()
            self.stdout.write(self.style.SUCCESS(f"  > {result['applied']} downgrade(s) applied."))

        if run_all or options['expire']:
            self.stdout.write(self.style.NOTICE('Expiring overdue subscriptions...'))
            result = expire_subscriptions()
            self.stdout.write(self.style.SUCCESS(f"  > {result['expired']} subscription(s) expired."))

        if run_all or options['reminders']:
            self.stdout.write(self.style.NOTICE('Sending expiry reminders...'))
            result = send_expiry_reminders()
            self.stdout.write(self.style.SUCCESS(f"  > {result['reminded']} reminder(s) sent."))

        self.stdout.write(self.style.SUCCESS('Done.'))
