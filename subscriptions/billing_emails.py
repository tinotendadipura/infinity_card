"""
Utility functions for sending professional HTML billing emails.

Covers:
  - Payment confirmation emails (personal subscriptions, card orders, company billing)
  - Billing reminder emails (personal + company subscriptions expiring soon)
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger('subscriptions')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PAYMENT_METHOD_LABELS = {
    'paypal': 'PayPal',
    'bank_transfer': 'Bank Transfer',
    'ecocash': 'EcoCash',
    'cash': 'Cash Payment',
}


def _logo_url():
    """Return an absolute URL for the InfinityCard logo used in emails."""
    if settings.DEBUG:
        return 'http://localhost:8000/static/images/logo_colour.png'
    return 'https://inftycard.cc/static/images/logo_colour.png'


def _dashboard_url(is_company=False):
    """Return an absolute URL for the dashboard."""
    if settings.DEBUG:
        base = 'http://localhost:8000'
    else:
        base = 'https://inftycard.cc'
    return f'{base}/company/billing/' if is_company else f'{base}/dashboard/'


def _billing_url(is_company=False):
    """Return an absolute URL for the billing page."""
    if settings.DEBUG:
        base = 'http://localhost:8000'
    else:
        base = 'https://inftycard.cc'
    return f'{base}/company/billing/' if is_company else f'{base}/billing/'


def _receipt_number(prefix, pk):
    """Generate a receipt-style number like INF-SUB-00042."""
    return f'INF-{prefix}-{pk:05d}'


def _send_billing_email(subject, to_email, context, template='emails/billing_confirmation.html'):
    """Render an HTML email template and send it."""
    context.setdefault('logo_url', _logo_url())
    html_body = render_to_string(template, context)

    # Plain-text fallback
    plain = (
        f"{context.get('description', 'Payment')} — "
        f"Amount: ${context.get('amount', '0.00')}. "
        f"Thank you for your payment. — InfinityCard"
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=plain,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    msg.attach_alternative(html_body, 'text/html')
    try:
        msg.send(fail_silently=False)
        logger.info('Billing email sent to %s: %s', to_email, subject)
    except Exception as exc:
        logger.error('Failed to send billing email to %s: %s', to_email, exc)


# ---------------------------------------------------------------------------
# Personal Subscription Confirmation
# ---------------------------------------------------------------------------

def send_subscription_confirmation(subscription, amount=None):
    """Send payment confirmation for a personal subscription activation/renewal."""
    user = subscription.user
    plan = subscription.plan
    period = subscription.billing_period

    if amount is None:
        amount = plan.yearly_price if period == 'yearly' else plan.price

    period_label = 'Yearly' if period == 'yearly' else 'Monthly'

    context = {
        'receipt_number': _receipt_number('SUB', subscription.pk),
        'date': timezone.now().strftime('%B %d, %Y'),
        'account_name': user.get_full_name() or user.username,
        'account_type': 'Personal',
        'description': f'{plan.name} Subscription',
        'billing_period': period_label,
        'payment_method': PAYMENT_METHOD_LABELS.get(subscription.payment_method, subscription.payment_method),
        'plan_name': plan.name,
        'amount': f'{amount:.2f}',
        'next_billing_date': subscription.expires_at.strftime('%B %d, %Y') if subscription.expires_at else None,
        'dashboard_url': _dashboard_url(is_company=False),
    }

    _send_billing_email(
        subject=f'Payment Confirmation — {plan.name} Subscription',
        to_email=user.email,
        context=context,
    )


# ---------------------------------------------------------------------------
# Personal Card Order Confirmation
# ---------------------------------------------------------------------------

def send_card_order_confirmation(order):
    """Send payment confirmation for a personal NFC card order."""
    user = order.user

    context = {
        'receipt_number': _receipt_number('ORD', order.pk),
        'date': timezone.now().strftime('%B %d, %Y'),
        'account_name': user.get_full_name() or user.username,
        'account_type': 'Personal',
        'description': f'NFC Card — {order.card_product.name}',
        'billing_period': None,
        'payment_method': PAYMENT_METHOD_LABELS.get(order.payment_method, order.payment_method),
        'plan_name': None,
        'amount': f'{order.amount:.2f}',
        'next_billing_date': None,
        'dashboard_url': _dashboard_url(is_company=False),
    }

    _send_billing_email(
        subject=f'Payment Confirmation — NFC Card Order #{order.pk}',
        to_email=user.email,
        context=context,
    )


# ---------------------------------------------------------------------------
# Company Subscription Confirmation
# ---------------------------------------------------------------------------

def send_company_subscription_confirmation(company_sub, amount=None):
    """Send payment confirmation for a company subscription activation/renewal."""
    company = company_sub.company
    plan = company_sub.plan
    period = company_sub.billing_period

    if amount is None:
        per_card = plan.yearly_price if period == 'yearly' else plan.price
        amount = per_card * company_sub.num_cards

    period_label = 'Yearly' if period == 'yearly' else 'Monthly'
    # Send to company owner email
    to_email = company.email or (company.owner.email if hasattr(company, 'owner') and company.owner else None)
    if not to_email:
        logger.warning('No email for company %s (pk=%d), skipping confirmation.', company.name, company.pk)
        return

    context = {
        'receipt_number': _receipt_number('CSUB', company_sub.pk),
        'date': timezone.now().strftime('%B %d, %Y'),
        'account_name': company.name,
        'account_type': 'Business',
        'description': f'{plan.name} Subscription ({company_sub.num_cards} cards)',
        'billing_period': period_label,
        'payment_method': PAYMENT_METHOD_LABELS.get(company_sub.payment_method, company_sub.payment_method),
        'plan_name': plan.name,
        'amount': f'{amount:.2f}',
        'next_billing_date': company_sub.expires_at.strftime('%B %d, %Y') if company_sub.expires_at else None,
        'dashboard_url': _dashboard_url(is_company=True),
    }

    _send_billing_email(
        subject=f'Payment Confirmation — {company.name} {plan.name} Subscription',
        to_email=to_email,
        context=context,
    )


# ---------------------------------------------------------------------------
# Company Card Order Confirmation
# ---------------------------------------------------------------------------

def send_company_order_confirmation(order):
    """Send payment confirmation for a company bulk NFC card order."""
    company = order.company
    to_email = (
        order.shipping_email
        or company.email
        or (company.owner.email if hasattr(company, 'owner') and company.owner else None)
    )
    if not to_email:
        logger.warning('No email for company order #%d, skipping confirmation.', order.pk)
        return

    context = {
        'receipt_number': _receipt_number('CORD', order.pk),
        'date': timezone.now().strftime('%B %d, %Y'),
        'account_name': company.name,
        'account_type': 'Business',
        'description': f'{order.quantity}x {order.card_product.name} NFC Cards',
        'billing_period': None,
        'payment_method': PAYMENT_METHOD_LABELS.get(order.payment_method, order.payment_method),
        'plan_name': None,
        'amount': f'{order.total_amount:.2f}',
        'next_billing_date': None,
        'dashboard_url': _dashboard_url(is_company=True),
    }

    _send_billing_email(
        subject=f'Payment Confirmation — {company.name} Bulk Order #{order.pk}',
        to_email=to_email,
        context=context,
    )


# ---------------------------------------------------------------------------
# Billing Reminder — Personal
# ---------------------------------------------------------------------------

def send_billing_reminder(subscription):
    """Send a billing reminder to a personal user whose subscription is expiring soon."""
    user = subscription.user
    plan = subscription.plan
    period = subscription.billing_period
    days_left = max((subscription.expires_at - timezone.now()).days, 0)

    renewal_amount = plan.yearly_price if period == 'yearly' else plan.price

    context = {
        'account_name': user.get_full_name() or user.username,
        'account_type': 'Personal',
        'plan_name': plan.name,
        'billing_period': 'Yearly' if period == 'yearly' else 'Monthly',
        'expires_at': subscription.expires_at.strftime('%B %d, %Y'),
        'days_remaining': days_left,
        'renewal_amount': f'{renewal_amount:.2f}',
        'billing_url': _billing_url(is_company=False),
    }

    _send_billing_email(
        subject=f'Your {plan.name} subscription expires in {days_left} day{"s" if days_left != 1 else ""}',
        to_email=user.email,
        context=context,
        template='emails/billing_reminder.html',
    )


# ---------------------------------------------------------------------------
# Billing Reminder — Company
# ---------------------------------------------------------------------------

def send_company_billing_reminder(company_sub):
    """Send a billing reminder to a company whose subscription is expiring soon."""
    company = company_sub.company
    plan = company_sub.plan
    period = company_sub.billing_period
    days_left = max((company_sub.expires_at - timezone.now()).days, 0)

    per_card = plan.yearly_price if period == 'yearly' else plan.price
    renewal_amount = per_card * company_sub.num_cards

    to_email = company.email or (company.owner.email if hasattr(company, 'owner') and company.owner else None)
    if not to_email:
        logger.warning('No email for company %s (pk=%d), skipping reminder.', company.name, company.pk)
        return

    context = {
        'account_name': company.name,
        'account_type': 'Business',
        'plan_name': plan.name,
        'billing_period': 'Yearly' if period == 'yearly' else 'Monthly',
        'expires_at': company_sub.expires_at.strftime('%B %d, %Y'),
        'days_remaining': days_left,
        'renewal_amount': f'{renewal_amount:.2f}',
        'billing_url': _billing_url(is_company=True),
    }

    _send_billing_email(
        subject=f'{company.name} subscription expires in {days_left} day{"s" if days_left != 1 else ""}',
        to_email=to_email,
        context=context,
        template='emails/billing_reminder.html',
    )
