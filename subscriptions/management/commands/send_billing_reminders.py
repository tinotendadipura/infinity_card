"""
Management command to send billing reminder emails to users and companies
whose subscriptions are expiring within the next 5 days.

Usage:
    python manage.py send_billing_reminders
    python manage.py send_billing_reminders --days 3
    python manage.py send_billing_reminders --dry-run

Can be scheduled via cron:
    0 8 * * * cd /path/to/project && python manage.py send_billing_reminders
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Send billing reminder emails to users/companies with subscriptions expiring soon.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=5,
            help='Number of days before expiry to send reminders (default: 5)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview which reminders would be sent without actually sending emails.',
        )

    def handle(self, *args, **options):
        from subscriptions.models import Subscription
        from subscriptions.billing_emails import send_billing_reminder, send_company_billing_reminder

        days = options['days']
        dry_run = options['dry_run']
        now = timezone.now()
        window = now + timedelta(days=days)

        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN — no emails will be sent.'))

        self.stdout.write(f'Checking for subscriptions expiring within {days} days (before {window.strftime("%b %d, %Y %H:%M")})...\n')

        # ── Personal subscriptions ──
        personal_subs = Subscription.objects.filter(
            status='active',
            expires_at__gt=now,
            expires_at__lte=window,
        ).select_related('plan', 'user')

        personal_count = 0
        for sub in personal_subs:
            days_left = (sub.expires_at - now).days
            if dry_run:
                self.stdout.write(
                    f'  [DRY] Would remind {sub.user.email} — '
                    f'{sub.plan.name} expires in {days_left} day(s) on {sub.expires_at.strftime("%b %d, %Y")}'
                )
            else:
                try:
                    send_billing_reminder(sub)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  ✓ Sent to {sub.user.email} — '
                            f'{sub.plan.name} expires in {days_left} day(s)'
                        )
                    )
                    personal_count += 1
                except Exception as exc:
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Failed for {sub.user.email}: {exc}')
                    )

        # ── Company subscriptions ──
        company_count = 0
        try:
            from companies.models import CompanySubscription
            company_subs = CompanySubscription.objects.filter(
                status='active',
                expires_at__gt=now,
                expires_at__lte=window,
            ).select_related('plan', 'company')

            for csub in company_subs:
                days_left = (csub.expires_at - now).days
                if dry_run:
                    self.stdout.write(
                        f'  [DRY] Would remind {csub.company.name} — '
                        f'{csub.plan.name} expires in {days_left} day(s) on {csub.expires_at.strftime("%b %d, %Y")}'
                    )
                else:
                    try:
                        send_company_billing_reminder(csub)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ Sent to {csub.company.name} — '
                                f'{csub.plan.name} expires in {days_left} day(s)'
                            )
                        )
                        company_count += 1
                    except Exception as exc:
                        self.stdout.write(
                            self.style.ERROR(f'  ✗ Failed for {csub.company.name}: {exc}')
                        )
        except ImportError:
            self.stdout.write('  (companies app not available, skipping company reminders)')

        # Summary
        total = personal_count + company_count
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\nDry run complete: {personal_subs.count()} personal + {company_subs.count() if "company_subs" in dir() else 0} company subscriptions eligible.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\nDone: {personal_count} personal + {company_count} company = {total} reminder(s) sent.'
            ))
