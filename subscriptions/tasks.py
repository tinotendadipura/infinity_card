"""
Celery periodic tasks for subscription lifecycle management.

Tasks:
  1. apply_pending_downgrades — switches subscriptions to their pending plan
     when the current billing period has ended.
  2. expire_subscriptions — marks active subscriptions as expired when
     their expires_at date has passed (and they have no pending downgrade).
  3. send_expiry_reminders — (placeholder) sends email reminders N days
     before a subscription expires.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('subscriptions')


@shared_task(name='subscriptions.apply_pending_downgrades')
def apply_pending_downgrades():
    """
    Apply scheduled downgrades for subscriptions whose billing period has ended.

    When a user downgrades, the change is stored in pending_plan / pending_period
    and only takes effect once expires_at is reached.  This task:
      1. Switches the subscription to the pending plan.
      2. Starts a fresh billing cycle on the new (cheaper) plan.
      3. Clears the pending fields.
      4. Creates a BillingEvent for audit.
    """
    from .models import Subscription, BillingEvent

    now = timezone.now()
    subs = Subscription.objects.filter(
        pending_plan__isnull=False,
        expires_at__lte=now,
        status__in=('active', 'cancelled'),
    ).select_related('pending_plan', 'plan', 'user')

    applied = 0
    for sub in subs:
        old_plan = sub.plan
        new_plan = sub.pending_plan
        new_period = sub.pending_period or sub.billing_period

        # Calculate new billing cycle
        period_days = 365 if new_period == 'yearly' else 30
        if new_period == 'yearly':
            new_amount = new_plan.yearly_price
        else:
            new_amount = new_plan.price

        # Apply the switch
        sub.plan = new_plan
        sub.billing_period = new_period
        sub.status = 'active'
        sub.expires_at = now + timedelta(days=period_days)
        sub.pending_plan = None
        sub.pending_period = ''
        sub.save()

        BillingEvent.objects.create(
            user=sub.user,
            event_type='downgrade',
            plan=new_plan,
            amount=new_amount,
            note=(
                f'Scheduled downgrade applied: {old_plan.name} → {new_plan.name} '
                f'({new_period}). New cycle ends {sub.expires_at.strftime("%b %d, %Y")}.'
            ),
        )
        applied += 1
        logger.info(
            'Applied pending downgrade for %s: %s → %s (%s)',
            sub.user.username, old_plan.name, new_plan.name, new_period,
        )

    logger.info('apply_pending_downgrades: %d subscription(s) processed.', applied)
    return {'applied': applied}


@shared_task(name='subscriptions.expire_subscriptions')
def expire_subscriptions():
    """
    Mark active subscriptions as expired when their billing period has ended
    and they have NO pending downgrade (those are handled by apply_pending_downgrades).
    """
    from .models import Subscription, BillingEvent

    now = timezone.now()
    subs = Subscription.objects.filter(
        status='active',
        expires_at__lte=now,
        pending_plan__isnull=True,
    ).select_related('plan', 'user')

    expired = 0
    for sub in subs:
        sub.status = 'expired'
        sub.save(update_fields=['status'])

        BillingEvent.objects.create(
            user=sub.user,
            event_type='cancel',
            plan=sub.plan,
            amount=Decimal('0.00'),
            note=f'Subscription expired (auto). {sub.plan.name} ({sub.billing_period}).',
        )
        expired += 1
        logger.info('Expired subscription for %s: %s', sub.user.username, sub.plan.name)

    logger.info('expire_subscriptions: %d subscription(s) expired.', expired)
    return {'expired': expired}


@shared_task(name='subscriptions.send_expiry_reminders')
def send_expiry_reminders():
    """
    Send HTML email reminders to users and companies whose subscriptions
    will expire in the next 5 days.

    Covers:
      • Personal subscriptions (Subscription model)
      • Company subscriptions (CompanySubscription model)
    """
    from .models import Subscription
    from .billing_emails import send_billing_reminder, send_company_billing_reminder

    now = timezone.now()
    window = now + timedelta(days=5)

    # ── Personal subscriptions ──
    personal_subs = Subscription.objects.filter(
        status='active',
        expires_at__gt=now,
        expires_at__lte=window,
    ).select_related('plan', 'user')

    personal_reminded = 0
    for sub in personal_subs:
        days_left = (sub.expires_at - now).days
        try:
            send_billing_reminder(sub)
            personal_reminded += 1
            logger.info(
                'Billing reminder sent to %s — %s expires in %d day(s).',
                sub.user.email, sub.plan.name, days_left,
            )
        except Exception as exc:
            logger.error('Failed to send reminder to %s: %s', sub.user.email, exc)

    # ── Company subscriptions ──
    try:
        from companies.models import CompanySubscription
        company_subs = CompanySubscription.objects.filter(
            status='active',
            expires_at__gt=now,
            expires_at__lte=window,
        ).select_related('plan', 'company')

        company_reminded = 0
        for csub in company_subs:
            days_left = (csub.expires_at - now).days
            try:
                send_company_billing_reminder(csub)
                company_reminded += 1
                logger.info(
                    'Company billing reminder sent for %s — %s expires in %d day(s).',
                    csub.company.name, csub.plan.name, days_left,
                )
            except Exception as exc:
                logger.error('Failed to send company reminder for %s: %s', csub.company.name, exc)
    except ImportError:
        company_reminded = 0

    total = personal_reminded + company_reminded
    logger.info('send_expiry_reminders: %d personal + %d company = %d reminder(s) sent.', personal_reminded, company_reminded, total)
    return {'personal_reminded': personal_reminded, 'company_reminded': company_reminded}
