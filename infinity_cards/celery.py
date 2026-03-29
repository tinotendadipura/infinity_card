"""
Celery application configuration for InfinityCard.

Usage:
  # Start the worker:
  celery -A infinity_cards worker --loglevel=info

  # Start the beat scheduler (periodic tasks):
  celery -A infinity_cards beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

  # Or run both in one process (dev only):
  celery -A infinity_cards worker --beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'infinity_cards.settings')

app = Celery('infinity_cards')

# Read config from Django settings, using the CELERY_ namespace.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py in every installed app.
app.autodiscover_tasks()
