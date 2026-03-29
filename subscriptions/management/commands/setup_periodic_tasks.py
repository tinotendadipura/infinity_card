"""
Management command to register Celery Beat periodic tasks in the database.

Usage:
  python manage.py setup_periodic_tasks

This creates (or updates) the following periodic tasks:
  1. apply_pending_downgrades — every hour
  2. expire_subscriptions — every hour
  3. send_expiry_reminders — once daily at 8:00 AM UTC
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Register Celery Beat periodic tasks for subscription lifecycle management.'

    def handle(self, *args, **options):
        from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule

        # ── Interval: every 1 hour ──
        hourly, _ = IntervalSchedule.objects.get_or_create(
            every=1, period=IntervalSchedule.HOURS,
        )

        # ── Crontab: daily at 08:00 UTC ──
        daily_8am, _ = CrontabSchedule.objects.get_or_create(
            minute='0', hour='8',
            day_of_week='*', day_of_month='*', month_of_year='*',
        )

        # 1. Apply pending downgrades — every hour
        task1, created1 = PeriodicTask.objects.update_or_create(
            name='Apply pending subscription downgrades',
            defaults={
                'task': 'subscriptions.apply_pending_downgrades',
                'interval': hourly,
                'enabled': True,
            },
        )
        status1 = 'created' if created1 else 'updated'
        self.stdout.write(self.style.SUCCESS(f'  [{status1}] {task1.name} — every 1 hour'))

        # 2. Expire overdue subscriptions — every hour
        task2, created2 = PeriodicTask.objects.update_or_create(
            name='Expire overdue subscriptions',
            defaults={
                'task': 'subscriptions.expire_subscriptions',
                'interval': hourly,
                'enabled': True,
            },
        )
        status2 = 'created' if created2 else 'updated'
        self.stdout.write(self.style.SUCCESS(f'  [{status2}] {task2.name} — every 1 hour'))

        # 3. Send expiry reminders — daily at 8:00 AM
        task3, created3 = PeriodicTask.objects.update_or_create(
            name='Send subscription expiry reminders',
            defaults={
                'task': 'subscriptions.send_expiry_reminders',
                'crontab': daily_8am,
                'interval': None,
                'enabled': True,
            },
        )
        status3 = 'created' if created3 else 'updated'
        self.stdout.write(self.style.SUCCESS(f'  [{status3}] {task3.name} — daily at 08:00 UTC'))

        self.stdout.write(self.style.SUCCESS('\nAll periodic tasks registered.'))
