import json
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Plan, Subscription, BillingEvent, Payment, SubscriptionProofOfPayment, BankingDetail
from . import paypal as paypal_api
from .billing_emails import (
    send_subscription_confirmation,
    send_card_order_confirmation,
    send_company_order_confirmation,
    send_company_subscription_confirmation,
)

logger = logging.getLogger(__name__)


def _get_bank_details_dict():
    """Get primary bank account as dict (backward-compatible with settings.BANK_DETAILS)."""
    primary = BankingDetail.get_primary()
    return primary.as_dict() if primary else {}


def _get_bank_accounts_qs():
    """Get all active bank accounts."""
    return BankingDetail.get_active()


def plans_page(request):
    plans = Plan.objects.all()
    current_plan_slug = None
    subscription = None
    if request.user.is_authenticated:
        try:
            subscription = request.user.subscription
            current_plan_slug = subscription.plan.slug
        except Subscription.DoesNotExist:
            pass

    if request.user.is_authenticated:
        return render(request, 'subscriptions/dashboard_plans.html', {
            'plans': plans,
            'current_plan_slug': current_plan_slug,
            'subscription': subscription,
        })

    return render(request, 'subscriptions/plans.html', {
        'plans': plans,
        'current_plan_slug': current_plan_slug,
    })


def _period_days(period):
    """Return the number of days for a billing period."""
    return 365 if period == 'yearly' else 30


def _period_amount(plan, period):
    """Return the charge amount for the given billing period."""
    return plan.yearly_price if period == 'yearly' else plan.price


def _period_label(period):
    return 'year' if period == 'yearly' else 'month'


def _get_enabled_payment_methods(user=None):
    """Get list of enabled payment method codes, filtered by user's country."""
    from .models import PaymentMethodSettings
    enabled_methods = PaymentMethodSettings.get_enabled_methods()
    
    # Filter payment methods based on user's country
    # Zimbabwe users (ZW) can use all methods, others only PayPal
    if user and user.country != 'ZW':
        enabled_methods = [m for m in enabled_methods if m == 'paypal']
    
    return enabled_methods


def _proration_credit(sub):
    """Calculate the unused credit on the current subscription.

    Returns a Decimal representing the dollar value of remaining unused days.
    """
    remaining = sub.days_remaining()
    total_days = _period_days(sub.billing_period)
    if remaining <= 0 or total_days <= 0:
        return Decimal('0.00')
    current_amount = _period_amount(sub.plan, sub.billing_period)
    credit = (current_amount * Decimal(remaining) / Decimal(total_days)).quantize(Decimal('0.01'))
    return credit


@login_required
def subscribe(request, plan_slug):
    """
    Subscribe to a plan. Accepts GET params: period, payment_method, ecocash_phone.

    Plan-change rules (industry standard):
      • **Upgrade** (new plan price > current): takes effect immediately;
        unused days on the old plan are prorated as a credit toward the
        new plan charge.  A fresh billing cycle starts.
      • **Downgrade** (new plan price < current): scheduled at the end of
        the current billing period — user keeps current features until
        expiry, then switches automatically.
      • **Same plan + period**: blocked (already subscribed).
    """
    from cards.models import CardOrder
    from companies.models import CompanyMembership

    # Gate: company members cannot subscribe individually
    if CompanyMembership.objects.filter(user=request.user, is_active=True).exists():
        messages.info(request, 'Your billing is managed by your company.')
        return redirect('profiles:dashboard')
    # Gate: user must have a delivered card to subscribe
    if not CardOrder.objects.filter(user=request.user, status='delivered').exists():
        messages.error(request, 'You need a delivered NFC card before you can subscribe to a plan.')
        return redirect('subscriptions:billing')

    plan = get_object_or_404(Plan, slug=plan_slug)
    period = request.GET.get('period', 'monthly')
    payment_method = request.GET.get('payment_method', 'paypal')
    ecocash_phone = request.GET.get('ecocash_phone', '').strip()

    if period not in ('monthly', 'yearly'):
        period = 'monthly'
    if payment_method not in ('paypal', 'bank_transfer', 'ecocash', 'cash'):
        payment_method = 'paypal'

    # Prevent duplicate cash payments: block if user has a suspended cash subscription awaiting approval
    if payment_method == 'cash':
        try:
            existing = request.user.subscription
            if existing.status == 'suspended' and existing.payment_method == 'cash':
                messages.error(
                    request,
                    'You already have a pending cash payment for a subscription. '
                    'Please wait for it to be approved or declined before subscribing again.'
                )
                return redirect('subscriptions:billing')
        except Subscription.DoesNotExist:
            pass

    days = _period_days(period)
    amount = _period_amount(plan, period)

    # ── Load existing subscription ──
    try:
        sub = request.user.subscription
        old_plan = sub.plan
    except Subscription.DoesNotExist:
        sub = None
        old_plan = None

    # ── Same plan + period: block ──
    if sub and old_plan.slug == plan_slug and sub.billing_period == period and sub.is_active():
        messages.info(request, f'You are already on the {plan.name} ({period}) plan.')
        return redirect('subscriptions:billing')

    # ── EcoCash: require phone number ──
    if payment_method == 'ecocash' and not ecocash_phone:
        messages.error(request, 'Please enter your EcoCash phone number.')
        return redirect('subscriptions:billing')

    # ── Determine change type for existing active subscriptions ──
    is_upgrade = False
    is_downgrade = False
    if sub and sub.is_active():
        new_amount = _period_amount(plan, period)
        old_amount = _period_amount(old_plan, sub.billing_period)
        if new_amount > old_amount:
            is_upgrade = True
        elif new_amount < old_amount:
            is_downgrade = True
        else:
            # Same effective price but different plan/period combo
            is_upgrade = True  # treat as upgrade (immediate switch)

    # ──────────────────────────────────────────────
    #  DOWNGRADE: schedule for end of current period
    # ──────────────────────────────────────────────
    if is_downgrade:
        sub.pending_plan = plan
        sub.pending_period = period
        sub.save(update_fields=['pending_plan', 'pending_period'])
        BillingEvent.objects.create(
            user=request.user, event_type='downgrade', plan=plan,
            amount=Decimal('0.00'),
            note=(
                f'Downgrade to {plan.name} ({period}) scheduled — '
                f'takes effect {sub.expires_at.strftime("%b %d, %Y")}'
            ),
        )
        messages.success(
            request,
            f'Your downgrade to {plan.name} ({period}) has been scheduled. '
            f'You\'ll keep your current {old_plan.name} features until '
            f'{sub.expires_at.strftime("%b %d, %Y")}, then automatically switch.'
        )
        return redirect('subscriptions:billing')

    # ──────────────────────────────────────────────
    #  UPGRADE (active sub): immediate switch + proration
    # ──────────────────────────────────────────────
    if is_upgrade:
        credit = _proration_credit(sub)
        prorated_amount = max(amount - credit, Decimal('0.00'))

        # Clear any pending downgrade since the user is now upgrading
        sub.pending_plan = None
        sub.pending_period = ''

        # Cash upgrade - no POP required
        if payment_method == 'cash':
            sub.plan = plan
            sub.status = 'suspended'
            sub.billing_period = period
            sub.payment_method = payment_method
            sub.save()
            BillingEvent.objects.create(
                user=request.user, event_type='upgrade', plan=plan,
                amount=Decimal('0.00'),
                note=(
                    f'Upgrade to {plan.name} ({period}) via Cash Payment — '
                    f'awaiting approval (${amount} − ${credit} credit = ${prorated_amount})'
                ),
            )
            messages.success(
                request,
                f'Upgrade to {plan.name} initiated! '
                f'Amount due: ${prorated_amount} (${amount} minus ${credit} unused credit). '
                f'Your subscription is pending. Please pay in cash and an admin will approve your subscription once payment is received.'
            )
            return redirect('subscriptions:billing')

        # Bank transfer upgrade - requires POP upload
        if payment_method == 'bank_transfer':
            sub.plan = plan
            sub.status = 'suspended'
            sub.billing_period = period
            sub.payment_method = payment_method
            sub.save()
            BillingEvent.objects.create(
                user=request.user, event_type='upgrade', plan=plan,
                amount=Decimal('0.00'),
                note=(
                    f'Upgrade to {plan.name} ({period}) via Bank Transfer — '
                    f'awaiting approval (${amount} − ${credit} credit = ${prorated_amount})'
                ),
            )
            messages.success(
                request,
                f'Upgrade to {plan.name} initiated! '
                f'Amount due: ${prorated_amount} (${amount} minus ${credit} unused credit). '
                f'Please transfer the amount and upload your proof of payment.'
            )
            return redirect('subscriptions:upload_subscription_pop')

        # EcoCash upgrade
        if payment_method == 'ecocash':
            messages.info(request, f'EcoCash payment initiated to {ecocash_phone}. Check your phone for the prompt.')
            return redirect('subscriptions:billing')

        # PayPal upgrade: redirect to PayPal subscribe flow
        return redirect(
            reverse('subscriptions:paypal_subscribe', args=[plan.slug]) + f'?period={period}'
        )

    # ──────────────────────────────────────────────
    #  NEW SUBSCRIPTION (no existing sub, or expired/suspended)
    # ──────────────────────────────────────────────

    # ── Cash Payment → No POP required, just pending for admin approval ──
    if payment_method == 'cash':
        if sub:
            sub.plan = plan
            sub.status = 'suspended'
            sub.billing_period = period
            sub.payment_method = payment_method
            sub.pending_plan = None
            sub.pending_period = ''
            sub.save()
        else:
            Subscription.objects.create(
                user=request.user, plan=plan, status='suspended',
                billing_period=period, payment_method=payment_method,
                expires_at=timezone.now(),
            )
        BillingEvent.objects.create(
            user=request.user, event_type='subscribe', plan=plan,
            amount=Decimal('0.00'),
            note=f'New {period} subscription to {plan.name} via Cash Payment — awaiting approval (${amount})',
        )
        messages.success(
            request,
            f'Subscription to {plan.name} initiated! Total: ${amount}/{_period_label(period)}. '
            f'Your subscription is pending. Please pay in cash and an admin will approve your subscription once payment is received.'
        )
        return redirect('subscriptions:billing')

    # ── Bank Transfer → POP upload page ──
    if payment_method == 'bank_transfer':
        if sub:
            sub.plan = plan
            sub.status = 'suspended'
            sub.billing_period = period
            sub.payment_method = payment_method
            sub.pending_plan = None
            sub.pending_period = ''
            sub.save()
        else:
            Subscription.objects.create(
                user=request.user, plan=plan, status='suspended',
                billing_period=period, payment_method=payment_method,
                expires_at=timezone.now(),
            )
        BillingEvent.objects.create(
            user=request.user, event_type='subscribe', plan=plan,
            amount=Decimal('0.00'),
            note=f'New {period} subscription to {plan.name} via Bank Transfer — awaiting POP (${amount})',
        )
        messages.success(
            request,
            f'Subscription to {plan.name} initiated! Total: ${amount}/{_period_label(period)}. '
            f'Please transfer the amount and upload your proof of payment.'
        )
        return redirect('subscriptions:upload_subscription_pop')

    # ── EcoCash ──
    if payment_method == 'ecocash':
        # PRODUCTION: Call EcoCash API here when available
        messages.info(request, f'EcoCash payment initiated to {ecocash_phone}. Check your phone for the prompt.')
        return redirect('subscriptions:billing')

    # ── PayPal ──
    # Redirect to PayPal subscribe flow
    return redirect(
        reverse('subscriptions:paypal_subscribe', args=[plan.slug]) + f'?period={period}'
    )


@login_required
def billing_dashboard(request):
    from companies.models import CompanyMembership, CompanySubscription
    from cards.models import CardOrder

    # Company-linked users cannot access personal billing
    if CompanyMembership.objects.filter(user=request.user, is_active=True).exists():
        messages.info(request, 'Your billing is managed by your company.')
        return redirect('profiles:dashboard')

    subscription = None
    billing_events = request.user.billing_events.all()[:20]

    try:
        subscription = request.user.subscription
    except Subscription.DoesNotExist:
        pass

    # Check if user is linked to a company (invited employee)
    company_membership = CompanyMembership.objects.filter(
        user=request.user, is_active=True
    ).select_related('company').first()

    company_subscription = None
    if company_membership:
        try:
            company_subscription = company_membership.company.subscription
        except CompanySubscription.DoesNotExist:
            pass

    # Check card delivery status for subscription gating
    has_delivered_card = CardOrder.objects.filter(
        user=request.user, status='delivered'
    ).exists()
    has_pending_order = CardOrder.objects.filter(
        user=request.user, status__in=['pending', 'paid', 'shipped']
    ).exists()

    # Declined cash orders — show notification banners to user
    declined_cash_orders = CardOrder.objects.filter(
        user=request.user, payment_method='cash', status='cancelled',
    ).exclude(rejection_reason='').order_by('-created_at')[:5]

    # Pending cash orders — show "awaiting approval" banner
    pending_cash_orders = CardOrder.objects.filter(
        user=request.user, payment_method='cash', status='pending'
    ).order_by('-created_at')[:5]

    return render(request, 'subscriptions/billing.html', {
        'subscription': subscription,
        'billing_events': billing_events,
        'plans': Plan.objects.all(),
        'company_membership': company_membership,
        'company_subscription': company_subscription,
        'has_delivered_card': has_delivered_card,
        'has_pending_order': has_pending_order,
        'bank_details': _get_bank_details_dict(),
        'bank_accounts': _get_bank_accounts_qs(),
        'enabled_payment_methods': _get_enabled_payment_methods(request.user),
        'declined_cash_orders': declined_cash_orders,
        'pending_cash_orders': pending_cash_orders,
    })


@login_required
def renew_subscription(request):
    """Redirect to PayPal for proper renewal payment instead of free extension."""
    try:
        sub = request.user.subscription
        period = sub.billing_period or 'monthly'
        # Route through PayPal if plan has a PayPal billing plan
        pp_plan_id = sub.plan.paypal_yearly_plan_id if period == 'yearly' else sub.plan.paypal_plan_id
        if pp_plan_id:
            return redirect(
                reverse('subscriptions:paypal_subscribe', args=[sub.plan.slug]) + f'?period={period}'
            )
        # Fallback for plans without PayPal
        return redirect(
            reverse('subscriptions:subscribe', args=[sub.plan.slug]) + f'?period={period}'
        )
    except Subscription.DoesNotExist:
        messages.error(request, 'No subscription to renew. Please choose a plan.')
        return redirect('subscriptions:plans')


@login_required
def cancel_subscription(request):
    if request.method != 'POST':
        return redirect('subscriptions:billing')

    try:
        sub = request.user.subscription

        # Cancel on PayPal side if there's a linked subscription
        if sub.paypal_subscription_id:
            try:
                paypal_api.cancel_subscription(sub.paypal_subscription_id)
            except Exception as e:
                logger.error('PayPal cancel failed: %s', e)

        sub.status = 'cancelled'
        sub.paypal_subscription_id = ''
        sub.save()

        BillingEvent.objects.create(
            user=request.user,
            event_type='cancel',
            plan=sub.plan,
            amount=0,
            note=f'Cancelled {sub.plan.name} — access until {sub.expires_at.strftime("%b %d, %Y")}',
        )
        messages.success(request, f'Subscription cancelled. You still have access until {sub.expires_at.strftime("%b %d, %Y")}.')
    except Subscription.DoesNotExist:
        messages.error(request, 'No active subscription to cancel.')

    return redirect('subscriptions:billing')


@login_required
def cancel_downgrade(request):
    """Cancel a scheduled downgrade, keeping the current plan."""
    if request.method != 'POST':
        return redirect('subscriptions:billing')

    try:
        sub = request.user.subscription
        if not sub.pending_plan:
            messages.info(request, 'No scheduled plan change to cancel.')
            return redirect('subscriptions:billing')

        old_pending = sub.pending_plan.name
        sub.pending_plan = None
        sub.pending_period = ''
        sub.save(update_fields=['pending_plan', 'pending_period'])

        messages.success(request, f'Scheduled downgrade to {old_pending} has been cancelled. You\'ll stay on {sub.plan.name}.')
    except Subscription.DoesNotExist:
        messages.error(request, 'No active subscription found.')

    return redirect('subscriptions:billing')


# ──────────────────────────────────────────────
#  Subscription POP Upload
# ──────────────────────────────────────────────

@login_required
def upload_subscription_pop(request):
    """Upload proof of payment for a bank transfer subscription."""
    from datetime import date

    try:
        sub = request.user.subscription
    except Subscription.DoesNotExist:
        messages.error(request, 'No subscription found.')
        return redirect('subscriptions:billing')

    if sub.payment_method not in ('bank_transfer', 'ecocash', 'cash'):
        messages.error(request, 'This subscription does not require a proof of payment upload.')
        return redirect('subscriptions:billing')

    if sub.status == 'active' and sub.is_active():
        messages.info(request, 'Your subscription is already active.')
        return redirect('subscriptions:billing')

    existing_pop = sub.proof_of_payments.filter(status='pending').first()

    # Calculate the expected amount
    amount = _period_amount(sub.plan, sub.billing_period)

    if request.method == 'POST':
        document = request.FILES.get('document')
        reference_number = request.POST.get('reference_number', '').strip()
        amount_paid = request.POST.get('amount_paid', '')
        payment_date = request.POST.get('payment_date', '')
        notes = request.POST.get('notes', '').strip()

        if not document:
            messages.error(request, 'Please upload a proof of payment document.')
            return redirect('subscriptions:upload_subscription_pop')

        try:
            amount_paid = Decimal(amount_paid)
        except Exception:
            messages.error(request, 'Please enter a valid payment amount.')
            return redirect('subscriptions:upload_subscription_pop')

        try:
            payment_date = date.fromisoformat(payment_date)
        except (ValueError, TypeError):
            payment_date = date.today()

        SubscriptionProofOfPayment.objects.create(
            subscription=sub,
            uploaded_by=request.user,
            payment_type=sub.payment_method,
            document=document,
            reference_number=reference_number,
            amount_paid=amount_paid,
            payment_date=payment_date,
            notes=notes,
        )

        messages.success(
            request,
            'Proof of payment uploaded successfully! We will review it and activate your subscription within 24 hours.'
        )
        return redirect('subscriptions:billing')

    return render(request, 'subscriptions/upload_subscription_pop.html', {
        'subscription': sub,
        'existing_pop': existing_pop,
        'amount': amount,
        'bank_details': _get_bank_details_dict(),
        'bank_accounts': _get_bank_accounts_qs(),
        'ecocash_details': django_settings.ECOCASH_DETAILS,
    })


# ──────────────────────────────────────────────
#  PayPal Subscription Flow
# ──────────────────────────────────────────────

@login_required
def paypal_subscribe(request, plan_slug):
    """
    Step 1: User clicks 'Subscribe via PayPal'.
    We create a PayPal Subscription and redirect them to approve it.
    """
    from cards.models import CardOrder
    from companies.models import CompanyMembership
    # Gate: company members cannot subscribe individually
    if CompanyMembership.objects.filter(user=request.user, is_active=True).exists():
        messages.info(request, 'Your billing is managed by your company.')
        return redirect('profiles:dashboard')
    # Gate: user must have a delivered card to subscribe
    if not CardOrder.objects.filter(user=request.user, status='delivered').exists():
        messages.error(request, 'You need a delivered NFC card before you can subscribe to a plan.')
        return redirect('subscriptions:billing')

    plan = get_object_or_404(Plan, slug=plan_slug)
    period = request.GET.get('period', 'monthly')
    if period not in ('monthly', 'yearly'):
        period = 'monthly'

    # Pick the correct PayPal plan ID
    pp_plan_id = plan.paypal_yearly_plan_id if period == 'yearly' else plan.paypal_plan_id
    if not pp_plan_id:
        messages.error(request, 'This plan is not yet available for PayPal checkout. Please contact support.')
        return redirect('subscriptions:billing')

    # Check if user already has this plan + period active
    try:
        existing = request.user.subscription
        if existing.plan_id == plan.id and existing.billing_period == period and existing.is_active():
            messages.info(request, f'You are already on the {plan.name} ({period}) plan.')
            return redirect('subscriptions:billing')
    except Subscription.DoesNotExist:
        pass

    # Build return URLs using Django's reverse()
    return_url = request.build_absolute_uri(
        reverse('subscriptions:paypal_return') + f'?plan_slug={plan.slug}&period={period}'
    )
    cancel_url = request.build_absolute_uri(
        reverse('subscriptions:paypal_cancel_return')
    )

    try:
        pp_sub_id, approval_url = paypal_api.create_subscription(
            paypal_plan_id=pp_plan_id,
            return_url=return_url,
            cancel_url=cancel_url,
            user_email=request.user.email,
        )
    except Exception as e:
        logger.error('PayPal create subscription failed: %s', e)
        messages.error(request, 'Unable to connect to PayPal. Please try again.')
        return redirect('subscriptions:billing')

    if not approval_url:
        messages.error(request, 'PayPal did not return an approval URL. Please try again.')
        return redirect('subscriptions:billing')

    # Store the pending info in session
    request.session['pending_paypal_sub_id'] = pp_sub_id
    request.session['pending_plan_slug'] = plan.slug
    request.session['pending_period'] = period

    return redirect(approval_url)


@login_required
def paypal_return(request):
    """
    Step 2: PayPal redirects here after the user approves.
    We verify the subscription is ACTIVE, then activate locally.
    """
    # Log all GET params for debugging
    logger.info('PayPal return GET params: %s', dict(request.GET))

    # PayPal sends subscription_id in the redirect URL
    pp_sub_id = request.GET.get('subscription_id', '')
    # Our custom params may be present or we fall back to session
    plan_slug = request.GET.get('plan_slug', '') or request.session.get('pending_plan_slug', '')
    period = request.GET.get('period', '') or request.session.get('pending_period', 'monthly')

    # If subscription_id not in URL, fall back to session
    if not pp_sub_id:
        pp_sub_id = request.session.get('pending_paypal_sub_id', '')

    if period not in ('monthly', 'yearly'):
        period = 'monthly'

    logger.info('PayPal return: sub_id=%s, plan_slug=%s, period=%s', pp_sub_id, plan_slug, period)

    # Clean up session
    request.session.pop('pending_paypal_sub_id', None)
    request.session.pop('pending_plan_slug', None)
    request.session.pop('pending_period', None)

    if not pp_sub_id or not plan_slug:
        messages.error(request, 'Missing subscription details. Please try again.')
        return redirect('subscriptions:billing')

    plan = get_object_or_404(Plan, slug=plan_slug)
    days = _period_days(period)
    amount = _period_amount(plan, period)

    # Verify with PayPal that the subscription is active
    try:
        pp_details = paypal_api.get_subscription_details(pp_sub_id)
        logger.info('PayPal subscription %s status: %s', pp_sub_id, pp_details.get('status'))
    except Exception as e:
        logger.error('PayPal get subscription details failed for %s: %s', pp_sub_id, e)
        # Even if verification fails, trust the redirect and activate locally
        # The webhook will update the status later if needed
        pp_details = {'status': 'APPROVED'}

    pp_status = pp_details.get('status', '')
    if pp_status not in ('ACTIVE', 'APPROVED', 'APPROVAL_PENDING'):
        messages.warning(
            request,
            f'Your PayPal subscription status is "{pp_status}". '
            'It may take a moment to activate. Please refresh or contact support.'
        )
        return redirect('subscriptions:billing')

    # Activate or update local subscription
    try:
        sub = request.user.subscription
        old_plan = sub.plan
        event_type = 'upgrade' if plan.price > old_plan.price else ('downgrade' if plan.price < old_plan.price else 'renew')

        # Cancel old PayPal subscription if switching plans
        if sub.paypal_subscription_id and sub.paypal_subscription_id != pp_sub_id:
            try:
                paypal_api.cancel_subscription(sub.paypal_subscription_id, reason='Switched plans')
            except Exception:
                pass

        sub.plan = plan
        sub.status = 'active'
        sub.billing_period = period
        sub.paypal_subscription_id = pp_sub_id
        sub.expires_at = timezone.now() + timedelta(days=days)
        sub.save()

        BillingEvent.objects.create(
            user=request.user,
            event_type=event_type,
            plan=plan,
            amount=amount,
            note=f'{event_type.title()} to {plan.name} ({period}) via PayPal ({pp_sub_id})',
        )
    except Subscription.DoesNotExist:
        Subscription.objects.create(
            user=request.user,
            plan=plan,
            status='active',
            billing_period=period,
            expires_at=timezone.now() + timedelta(days=days),
            paypal_subscription_id=pp_sub_id,
        )
        BillingEvent.objects.create(
            user=request.user,
            event_type='subscribe',
            plan=plan,
            amount=amount,
            note=f'New {period} subscription to {plan.name} via PayPal ({pp_sub_id})',
        )

    # Send subscription confirmation email
    sub = request.user.subscription
    send_subscription_confirmation(sub, amount=amount)

    messages.success(request, f'Successfully subscribed to {plan.name} ({period})! Welcome aboard.')
    return redirect('subscriptions:billing')


@login_required
def paypal_cancel_return(request):
    """User cancelled the PayPal approval flow."""
    request.session.pop('pending_paypal_sub_id', None)
    request.session.pop('pending_plan_slug', None)
    messages.info(request, 'PayPal checkout was cancelled. No changes were made.')
    return redirect('subscriptions:billing')


@csrf_exempt
@require_POST
def paypal_webhook(request):
    """
    Handles PayPal webhook events for recurring billing.
    Key events:
      - BILLING.SUBSCRIPTION.ACTIVATED
      - PAYMENT.SALE.COMPLETED
      - BILLING.SUBSCRIPTION.CANCELLED
      - BILLING.SUBSCRIPTION.SUSPENDED
      - BILLING.SUBSCRIPTION.EXPIRED
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_type = body.get('event_type', '')
    resource = body.get('resource', {})

    logger.info('PayPal webhook: %s', event_type)

    # ── Recurring payment completed ──
    if event_type == 'PAYMENT.SALE.COMPLETED':
        pp_sub_id = resource.get('billing_agreement_id', '')
        if not pp_sub_id:
            return HttpResponse(status=200)

        try:
            sub = Subscription.objects.get(paypal_subscription_id=pp_sub_id)
        except Subscription.DoesNotExist:
            logger.warning('Webhook: no local subscription for PayPal sub %s', pp_sub_id)
            return HttpResponse(status=200)

        amount_str = resource.get('amount', {}).get('total', '0')
        currency = resource.get('amount', {}).get('currency', 'USD')
        sale_id = resource.get('id', '')
        create_time = resource.get('create_time', '')

        # Avoid duplicate payments
        if sale_id and not Payment.objects.filter(paypal_payment_id=sale_id).exists():
            Payment.objects.create(
                user=sub.user,
                subscription=sub,
                paypal_payment_id=sale_id,
                amount=Decimal(amount_str),
                currency=currency,
                status='COMPLETED',
                paid_at=parse_datetime(create_time) or timezone.now(),
                raw_data=body,
            )

        # Extend subscription based on billing period
        ext_days = _period_days(sub.billing_period)
        sub.expires_at = max(sub.expires_at, timezone.now()) + timedelta(days=ext_days)
        sub.status = 'active'
        sub.save()

        BillingEvent.objects.create(
            user=sub.user,
            event_type='renew',
            plan=sub.plan,
            amount=Decimal(amount_str),
            note=f'Auto-renewal via PayPal ({sale_id})',
        )
        logger.info('Renewed subscription for user %s via webhook', sub.user.username)

    # ── Subscription cancelled / suspended / expired ──
    elif event_type in (
        'BILLING.SUBSCRIPTION.CANCELLED',
        'BILLING.SUBSCRIPTION.SUSPENDED',
        'BILLING.SUBSCRIPTION.EXPIRED',
    ):
        pp_sub_id = resource.get('id', '')
        try:
            sub = Subscription.objects.get(paypal_subscription_id=pp_sub_id)
            if event_type == 'BILLING.SUBSCRIPTION.SUSPENDED':
                sub.status = 'suspended'
            else:
                sub.status = 'expired'
            sub.save()

            BillingEvent.objects.create(
                user=sub.user,
                event_type='cancel',
                plan=sub.plan,
                amount=0,
                note=f'PayPal webhook: {event_type}',
            )
            logger.info('Subscription %s updated to %s via webhook', pp_sub_id, sub.status)
        except Subscription.DoesNotExist:
            logger.warning('Webhook: no local subscription for %s', pp_sub_id)

    # ── Subscription activated (first approval) ──
    elif event_type == 'BILLING.SUBSCRIPTION.ACTIVATED':
        pp_sub_id = resource.get('id', '')
        logger.info('PayPal subscription %s activated (handled at return URL)', pp_sub_id)

    return HttpResponse(status=200)


# ──────────────────────────────────────────────
#  Super-Admin Management Dashboard  (multi-page)
# ──────────────────────────────────────────────

def _admin_ctx(request):
    """Shared context for admin sidebar badge counts."""
    from cards.models import PersonalProofOfPayment
    from companies.models import ProofOfPayment
    personal_pending = PersonalProofOfPayment.objects.filter(status='pending').count()
    company_pending = ProofOfPayment.objects.filter(status='pending').count()
    subscription_pending = SubscriptionProofOfPayment.objects.filter(status='pending').count()
    return {'pending_pop_count': personal_pending + company_pending + subscription_pending}


@staff_member_required
def admin_dashboard(request):
    """Main overview dashboard with key stats."""
    from django.contrib.auth import get_user_model
    from cards.models import CardOrder
    from companies.models import BulkCardOrder, ProofOfPayment
    from cards.models import PersonalProofOfPayment
    User = get_user_model()
    now = timezone.now()

    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    total_subscriptions = Subscription.objects.count()
    active_subs = Subscription.objects.filter(status='active', expires_at__gt=now).count()
    expired_subs = Subscription.objects.filter(Q(status='expired') | Q(expires_at__lte=now)).count()
    sub_revenue = BillingEvent.objects.filter(
        event_type__in=('subscribe', 'upgrade', 'renew', 'downgrade'),
        amount__gt=0,
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Card orders
    personal_orders_pending = CardOrder.objects.filter(status='pending').count()
    personal_orders_paid = CardOrder.objects.filter(status__in=['paid', 'shipped']).count()
    card_revenue = CardOrder.objects.filter(status='paid').aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Bulk orders
    bulk_orders_pending = BulkCardOrder.objects.filter(status='pending').count()
    bulk_orders_paid = BulkCardOrder.objects.filter(status__in=['paid', 'shipped']).count()
    bulk_revenue = BulkCardOrder.objects.filter(status='paid').aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

    # POP pending
    personal_pop_pending = PersonalProofOfPayment.objects.filter(status='pending').count()
    company_pop_pending = ProofOfPayment.objects.filter(status='pending').count()

    # Recent activity
    recent_orders = CardOrder.objects.select_related('user', 'card_product').order_by('-created_at')[:5]
    recent_bulk = BulkCardOrder.objects.select_related('company', 'card_product').order_by('-created_at')[:5]
    recent_events = BillingEvent.objects.select_related('user', 'plan').order_by('-created_at')[:10]

    ctx = {
        'total_users': total_users,
        'active_users': active_users,
        'total_subscriptions': total_subscriptions,
        'active_subs': active_subs,
        'expired_subs': expired_subs,
        'sub_revenue': sub_revenue,
        'personal_orders_pending': personal_orders_pending,
        'personal_orders_paid': personal_orders_paid,
        'card_revenue': card_revenue,
        'bulk_orders_pending': bulk_orders_pending,
        'bulk_orders_paid': bulk_orders_paid,
        'bulk_revenue': bulk_revenue,
        'personal_pop_pending': personal_pop_pending,
        'company_pop_pending': company_pop_pending,
        'recent_orders': recent_orders,
        'recent_bulk': recent_bulk,
        'recent_events': recent_events,
    }
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_dashboard.html', ctx)


# ── Card Orders ──

@staff_member_required
def admin_orders(request):
    """Personal card orders list with filtering."""
    from cards.models import CardOrder
    status_filter = request.GET.get('status', '')
    qs = CardOrder.objects.select_related('user', 'card_product').order_by('-created_at')
    if status_filter:
        qs = qs.filter(status=status_filter)
    ctx = {'orders': qs[:100], 'status_filter': status_filter, 'plans': Plan.objects.all()}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_orders.html', ctx)


# ── Bulk Orders ──

@staff_member_required
def admin_bulk_orders(request):
    """Company bulk orders list."""
    from companies.models import BulkCardOrder
    status_filter = request.GET.get('status', '')
    qs = BulkCardOrder.objects.select_related('company', 'card_product', 'ordered_by').order_by('-created_at')
    if status_filter:
        qs = qs.filter(status=status_filter)
    ctx = {'orders': qs[:100], 'status_filter': status_filter}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_bulk_orders.html', ctx)


@staff_member_required
def admin_bulk_order_action(request, order_id):
    """Actions on bulk orders: mark paid, shipped, delivered."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_bulk_orders')
    from companies.models import BulkCardOrder
    order = get_object_or_404(BulkCardOrder, pk=order_id)
    action = request.POST.get('action', '')

    if action == 'mark_paid' and order.status == 'pending':
        order.status = 'paid'
        order.paid_at = timezone.now()
        order.save(update_fields=['status', 'paid_at'])
        messages.success(request, f'Bulk order #{order.pk} marked as paid.')
    elif action == 'mark_shipped' and order.status == 'paid':
        order.status = 'shipped'
        order.shipped_at = timezone.now()
        order.save(update_fields=['status', 'shipped_at'])
        messages.success(request, f'Bulk order #{order.pk} marked as shipped.')
    elif action == 'mark_delivered' and order.status == 'shipped':
        order.status = 'delivered'
        order.delivered_at = timezone.now()
        order.save(update_fields=['status', 'delivered_at'])
        messages.success(request, f'Bulk order #{order.pk} marked as delivered.')
    else:
        messages.error(request, f'Invalid action "{action}" for order status "{order.get_status_display()}".')

    return redirect('subscriptions:admin_bulk_orders')


# ── Payment Approvals (POP) ──

@staff_member_required
def admin_approvals(request):
    """Pending proof-of-payment approvals for personal, company, and subscription payments."""
    from cards.models import PersonalProofOfPayment, CardOrder
    from companies.models import ProofOfPayment, BulkCardOrder

    tab = request.GET.get('tab', 'personal')
    status_filter = request.GET.get('status', 'pending')

    # Personal POPs (bank transfer, ecocash)
    personal_pops = PersonalProofOfPayment.objects.select_related(
        'order', 'order__user', 'uploaded_by'
    ).order_by('-created_at')
    if status_filter:
        personal_pops = personal_pops.filter(status=status_filter)

    # Personal cash orders (no POP required)
    personal_cash_orders = CardOrder.objects.filter(
        payment_method='cash'
    ).select_related('user').order_by('-created_at')
    if status_filter == 'pending':
        personal_cash_orders = personal_cash_orders.filter(status='pending')
    elif status_filter == 'approved':
        personal_cash_orders = personal_cash_orders.filter(status__in=['paid', 'shipped', 'delivered'])
    elif status_filter == 'rejected':
        personal_cash_orders = personal_cash_orders.filter(status='cancelled')
    else:
        # Default to pending if no filter or "all"
        if not status_filter:
            personal_cash_orders = personal_cash_orders.filter(status='pending')

    # Company POPs (bank transfer, ecocash)
    company_pops = ProofOfPayment.objects.select_related(
        'order', 'order__company', 'uploaded_by'
    ).order_by('-created_at')
    if status_filter:
        company_pops = company_pops.filter(status=status_filter)

    # Company cash orders (no POP required)
    company_cash_orders = BulkCardOrder.objects.filter(
        payment_method='cash'
    ).select_related('company', 'ordered_by').order_by('-created_at')
    if status_filter == 'pending':
        company_cash_orders = company_cash_orders.filter(status='pending')
    elif status_filter == 'approved':
        company_cash_orders = company_cash_orders.filter(status__in=['paid', 'shipped', 'delivered'])
    elif status_filter == 'rejected':
        company_cash_orders = company_cash_orders.filter(status='cancelled')
    else:
        # Default to pending if no filter or "all"
        if not status_filter:
            company_cash_orders = company_cash_orders.filter(status='pending')

    # Subscription POPs (bank transfer, ecocash)
    subscription_pops = SubscriptionProofOfPayment.objects.select_related(
        'subscription', 'subscription__user', 'subscription__plan', 'uploaded_by'
    ).order_by('-created_at')
    if status_filter:
        subscription_pops = subscription_pops.filter(status=status_filter)

    # Cash subscriptions (no POP required)
    cash_subscriptions = Subscription.objects.filter(
        payment_method='cash',
        status='suspended'
    ).select_related('user', 'plan').order_by('-started_at')

    # Calculate pending counts for tab badges
    personal_pending_count = (
        PersonalProofOfPayment.objects.filter(status='pending').count() +
        CardOrder.objects.filter(payment_method='cash', status='pending').count()
    )
    company_pending_count = (
        ProofOfPayment.objects.filter(status='pending').count() +
        BulkCardOrder.objects.filter(payment_method='cash', status='pending').count()
    )
    subscription_pending_count = (
        SubscriptionProofOfPayment.objects.filter(status='pending').count() +
        Subscription.objects.filter(payment_method='cash', status='suspended').count()
    )

    ctx = {
        'personal_pops': personal_pops[:100],
        'personal_cash_orders': personal_cash_orders[:100],
        'company_pops': company_pops[:100],
        'company_cash_orders': company_cash_orders[:100],
        'subscription_pops': subscription_pops[:100],
        'cash_subscriptions': cash_subscriptions[:100],
        'tab': tab,
        'status_filter': status_filter,
        'personal_pending_count': personal_pending_count,
        'company_pending_count': company_pending_count,
        'subscription_pending_count': subscription_pending_count,
    }
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_approvals.html', ctx)


@staff_member_required
def admin_approve_personal_pop(request, pop_id):
    """Approve a personal proof of payment and mark order as paid."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')
    from cards.models import PersonalProofOfPayment

    pop = get_object_or_404(PersonalProofOfPayment, pk=pop_id)
    if pop.status != 'pending':
        messages.info(request, f'POP #{pop.pk} already {pop.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')

    pop.status = 'approved'
    pop.reviewed_by = request.user
    pop.reviewed_at = timezone.now()
    pop.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

    order = pop.order
    if order.status == 'pending':
        order.status = 'paid'
        order.paid_at = timezone.now()
        order.save(update_fields=['status', 'paid_at'])

    # Send payment confirmation email
    send_card_order_confirmation(order)

    messages.success(request, f'POP #{pop.pk} approved — order #{order.pk} marked as paid.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_reject_personal_pop(request, pop_id):
    """Reject a personal proof of payment."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')
    from cards.models import PersonalProofOfPayment

    pop = get_object_or_404(PersonalProofOfPayment, pk=pop_id)
    if pop.status != 'pending':
        messages.info(request, f'POP #{pop.pk} already {pop.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')

    reason = request.POST.get('reason', '')
    pop.status = 'rejected'
    pop.reviewed_by = request.user
    pop.reviewed_at = timezone.now()
    pop.rejection_reason = reason
    pop.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])

    messages.success(request, f'POP #{pop.pk} rejected.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_approve_company_pop(request, pop_id):
    """Approve a company proof of payment, mark order paid, create card assignments."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')
    from companies.models import ProofOfPayment, CardAssignment

    pop = get_object_or_404(ProofOfPayment, pk=pop_id)
    if pop.status != 'pending':
        messages.info(request, f'POP #{pop.pk} already {pop.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')

    pop.status = 'approved'
    pop.reviewed_by = request.user
    pop.reviewed_at = timezone.now()
    pop.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

    order = pop.order
    if order.status == 'pending':
        order.status = 'paid'
        order.paid_at = timezone.now()
        order.save(update_fields=['status', 'paid_at'])

        # Create card assignments
        company = order.company
        session_members = order.members.all()
        if session_members.exists():
            for m in session_members:
                if not CardAssignment.objects.filter(company=company, bulk_order=order, membership=m).exists():
                    CardAssignment.objects.create(
                        company=company, membership=m, bulk_order=order,
                        card_product=order.card_product, status='assigned',
                        assigned_at=timezone.now(),
                    )
            remaining = order.quantity - session_members.count()
            for _ in range(max(0, remaining)):
                CardAssignment.objects.create(
                    company=company, bulk_order=order,
                    card_product=order.card_product, status='unassigned',
                )
        else:
            for _ in range(order.quantity):
                CardAssignment.objects.create(
                    company=company, bulk_order=order,
                    card_product=order.card_product, status='unassigned',
                )

    # Send payment confirmation email
    send_company_order_confirmation(order)

    messages.success(request, f'POP #{pop.pk} approved — bulk order #{order.pk} activated.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_reject_company_pop(request, pop_id):
    """Reject a company proof of payment."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')
    from companies.models import ProofOfPayment

    pop = get_object_or_404(ProofOfPayment, pk=pop_id)
    if pop.status != 'pending':
        messages.info(request, f'POP #{pop.pk} already {pop.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')

    reason = request.POST.get('reason', '')
    pop.status = 'rejected'
    pop.reviewed_by = request.user
    pop.reviewed_at = timezone.now()
    pop.rejection_reason = reason
    pop.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])

    messages.success(request, f'POP #{pop.pk} rejected.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_approve_cash_order(request, order_id):
    """Approve a personal cash payment order and mark it as paid."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')
    
    from cards.models import CardOrder
    
    order = get_object_or_404(CardOrder, pk=order_id, payment_method='cash')
    if order.status != 'pending':
        messages.info(request, f'Order #{order.pk} is already {order.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')
    
    order.status = 'paid'
    order.paid_at = timezone.now()
    order.save(update_fields=['status', 'paid_at'])

    # Send payment confirmation email
    send_card_order_confirmation(order)
    
    messages.success(request, f'Cash payment approved — order #{order.pk} marked as paid.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_approve_company_cash_order(request, order_id):
    """Approve a company cash payment order, mark it paid, and create card assignments."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')
    
    from companies.models import BulkCardOrder, CardAssignment
    
    order = get_object_or_404(BulkCardOrder, pk=order_id, payment_method='cash')
    if order.status != 'pending':
        messages.info(request, f'Order #{order.pk} is already {order.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')
    
    order.status = 'paid'
    order.paid_at = timezone.now()
    order.save(update_fields=['status', 'paid_at'])
    
    # Create card assignments
    company = order.company
    session_members = order.members.all()
    if session_members.exists():
        for m in session_members:
            if not CardAssignment.objects.filter(company=company, bulk_order=order, membership=m).exists():
                CardAssignment.objects.create(
                    company=company, membership=m, bulk_order=order,
                    card_product=order.card_product, status='assigned',
                    assigned_at=timezone.now(),
                )
        remaining = order.quantity - session_members.count()
        for _ in range(max(0, remaining)):
            CardAssignment.objects.create(
                company=company, bulk_order=order,
                card_product=order.card_product, status='unassigned',
            )
    else:
        for _ in range(order.quantity):
            CardAssignment.objects.create(
                company=company, bulk_order=order,
                card_product=order.card_product, status='unassigned',
            )
    
    # Send payment confirmation email
    send_company_order_confirmation(order)

    messages.success(request, f'Cash payment approved — bulk order #{order.pk} activated.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_approve_subscription_pop(request, pop_id):
    """Approve a subscription proof of payment and activate the subscription."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')

    pop = get_object_or_404(SubscriptionProofOfPayment, pk=pop_id)
    if pop.status != 'pending':
        messages.info(request, f'POP #{pop.pk} already {pop.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')

    pop.status = 'approved'
    pop.reviewed_by = request.user
    pop.reviewed_at = timezone.now()
    pop.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

    # Activate the subscription
    sub = pop.subscription
    if sub.status == 'suspended':
        days = _period_days(sub.billing_period)
        sub.status = 'active'
        sub.expires_at = timezone.now() + timedelta(days=days)
        sub.save(update_fields=['status', 'expires_at'])

        BillingEvent.objects.create(
            user=sub.user,
            event_type='subscribe',
            plan=sub.plan,
            amount=pop.amount_paid,
            note=f'{sub.plan.name} ({sub.billing_period}) activated via {pop.get_payment_type_display()} POP approval',
        )

    # Send subscription confirmation email
    send_subscription_confirmation(sub, amount=pop.amount_paid)

    messages.success(request, f'POP #{pop.pk} approved — {sub.user.username}\'s {sub.plan.name} subscription activated.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_reject_subscription_pop(request, pop_id):
    """Reject a subscription proof of payment."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')

    pop = get_object_or_404(SubscriptionProofOfPayment, pk=pop_id)
    if pop.status != 'pending':
        messages.info(request, f'POP #{pop.pk} already {pop.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')

    reason = request.POST.get('reason', '')
    pop.status = 'rejected'
    pop.reviewed_by = request.user
    pop.reviewed_at = timezone.now()
    pop.rejection_reason = reason
    pop.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])

    messages.success(request, f'POP #{pop.pk} rejected.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_approve_cash_subscription(request, sub_id):
    """Approve a cash payment subscription and activate it."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')
    
    sub = get_object_or_404(Subscription, pk=sub_id, payment_method='cash')
    if sub.status != 'suspended':
        messages.info(request, f'Subscription #{sub.pk} is already {sub.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')
    
    # Activate subscription
    from datetime import timedelta
    days = 30 if sub.billing_period == 'monthly' else 365
    sub.status = 'active'
    sub.started_at = timezone.now()
    sub.expires_at = timezone.now() + timedelta(days=days)
    sub.save(update_fields=['status', 'started_at', 'expires_at'])
    
    # Calculate amount based on plan and period
    amount = sub.plan.price if sub.billing_period == 'monthly' else sub.plan.yearly_price
    
    BillingEvent.objects.create(
        user=sub.user,
        event_type='subscribe',
        plan=sub.plan,
        amount=amount,
        note=f'{sub.plan.name} ({sub.billing_period}) activated via Cash Payment approval',
    )
    
    # Send subscription confirmation email
    send_subscription_confirmation(sub, amount=amount)

    messages.success(request, f'Cash payment approved — {sub.user.username}\'s {sub.plan.name} subscription activated.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_decline_cash_order(request, order_id):
    """Decline a personal cash payment order."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')

    from cards.models import CardOrder

    order = get_object_or_404(CardOrder, pk=order_id, payment_method='cash')
    if order.status != 'pending':
        messages.info(request, f'Order #{order.pk} is already {order.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')

    reason = request.POST.get('reason', '').strip()
    order.status = 'cancelled'
    order.rejection_reason = reason or 'Payment declined by administrator.'
    order.save(update_fields=['status', 'rejection_reason'])

    messages.success(request, f'Cash order #{order.pk} declined.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_decline_company_cash_order(request, order_id):
    """Decline a company cash payment order."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')

    from companies.models import BulkCardOrder

    order = get_object_or_404(BulkCardOrder, pk=order_id, payment_method='cash')
    if order.status != 'pending':
        messages.info(request, f'Order #{order.pk} is already {order.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')

    reason = request.POST.get('reason', '').strip()
    order.status = 'cancelled'
    order.rejection_reason = reason or 'Payment declined by administrator.'
    order.save(update_fields=['status', 'rejection_reason'])

    messages.success(request, f'Company cash order #{order.pk} declined.')
    return redirect('subscriptions:admin_approvals')


@staff_member_required
def admin_decline_cash_subscription(request, sub_id):
    """Decline a cash payment subscription — cancel it and store reason."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_approvals')

    sub = get_object_or_404(Subscription, pk=sub_id, payment_method='cash')
    if sub.status != 'suspended':
        messages.info(request, f'Subscription #{sub.pk} is already {sub.get_status_display()}.')
        return redirect('subscriptions:admin_approvals')

    reason = request.POST.get('reason', '').strip()
    sub.status = 'cancelled'
    sub.save(update_fields=['status'])

    BillingEvent.objects.create(
        user=sub.user,
        event_type='cancel',
        plan=sub.plan,
        amount=Decimal('0.00'),
        note=f'Cash payment declined: {reason}' if reason else 'Cash payment declined by administrator.',
    )

    messages.success(request, f'Cash subscription for {sub.user.username} declined.')
    return redirect('subscriptions:admin_approvals')


# ── Subscriptions ──

@staff_member_required
def admin_subscriptions(request):
    """All subscriptions list."""
    status_filter = request.GET.get('status', '')
    qs = Subscription.objects.select_related('user', 'plan').order_by('-started_at')
    if status_filter:
        qs = qs.filter(status=status_filter)
    ctx = {'subscriptions': qs[:100], 'status_filter': status_filter, 'plans': Plan.objects.all()}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_subscriptions.html', ctx)


# ── Plans ──

@staff_member_required
def admin_plans(request):
    """Manage plans and discounts."""
    plan_stats = Plan.objects.annotate(
        subscriber_count=Count('subscription', filter=Q(subscription__status='active'))
    ).order_by('price')
    ctx = {'plan_stats': plan_stats}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_plans.html', ctx)


# ── Users ──

@staff_member_required
def admin_users(request):
    """User accounts management."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')

    qs = User.objects.all().order_by('-date_joined')
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if status_filter == 'active':
        qs = qs.filter(is_active=True)
    elif status_filter == 'inactive':
        qs = qs.filter(is_active=False)
    if type_filter:
        qs = qs.filter(account_type=type_filter)

    ctx = {'users': qs[:100], 'q': q, 'status_filter': status_filter, 'type_filter': type_filter}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_users.html', ctx)


@staff_member_required
def admin_user_action(request, user_id):
    """Activate / deactivate / toggle staff on a user."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_users')
    from django.contrib.auth import get_user_model
    User = get_user_model()
    target = get_object_or_404(User, pk=user_id)
    action = request.POST.get('action', '')

    if action == 'activate':
        target.is_active = True
        target.save(update_fields=['is_active'])
        messages.success(request, f'{target.email} activated.')
    elif action == 'deactivate':
        if target == request.user:
            messages.error(request, 'You cannot deactivate your own account.')
        else:
            target.is_active = False
            target.save(update_fields=['is_active'])
            messages.success(request, f'{target.email} deactivated.')
    elif action == 'make_staff':
        target.is_staff = True
        target.save(update_fields=['is_staff'])
        messages.success(request, f'{target.email} granted staff access.')
    elif action == 'remove_staff':
        if target == request.user:
            messages.error(request, 'You cannot remove your own staff access.')
        else:
            target.is_staff = False
            target.save(update_fields=['is_staff'])
            messages.success(request, f'{target.email} staff access removed.')

    return redirect('subscriptions:admin_users')


@staff_member_required
def admin_update_subscription(request, sub_id):
    """Admin action to update a user's subscription (extend, cancel, change plan/period)."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_dashboard')

    sub = get_object_or_404(Subscription, pk=sub_id)
    action = request.POST.get('action')

    if action == 'extend':
        days = _period_days(sub.billing_period)
        sub.expires_at = max(sub.expires_at, timezone.now()) + timedelta(days=days)
        sub.status = 'active'
        sub.save()
        BillingEvent.objects.create(
            user=sub.user,
            event_type='renew',
            plan=sub.plan,
            amount=0,
            note=f'Extended by admin for 1 {_period_label(sub.billing_period)}',
        )
        messages.success(request, f'Extended {sub.user.username} by 1 {_period_label(sub.billing_period)}.')

    elif action == 'cancel':
        if sub.paypal_subscription_id:
            try:
                paypal_api.cancel_subscription(sub.paypal_subscription_id, reason='Cancelled by admin')
            except Exception as e:
                logger.error('Admin PayPal cancel failed: %s', e)
        sub.status = 'expired'
        sub.paypal_subscription_id = ''
        sub.save()
        BillingEvent.objects.create(
            user=sub.user,
            event_type='cancel',
            plan=sub.plan,
            amount=0,
            note='Cancelled by admin',
        )
        messages.success(request, f'Cancelled subscription for {sub.user.username}.')

    elif action == 'change_plan':
        new_plan_id = request.POST.get('plan_id')
        new_period = request.POST.get('period', sub.billing_period)
        if new_period not in ('monthly', 'yearly'):
            new_period = 'monthly'
        if new_plan_id:
            try:
                new_plan = Plan.objects.get(pk=new_plan_id)
                old_plan = sub.plan
                sub.plan = new_plan
                sub.billing_period = new_period
                sub.save()
                BillingEvent.objects.create(
                    user=sub.user,
                    event_type='upgrade' if new_plan.price > old_plan.price else 'downgrade',
                    plan=new_plan,
                    amount=0,
                    note=f'Changed from {old_plan.name} to {new_plan.name} ({new_period}) by admin',
                )
                messages.success(request, f'Changed {sub.user.username} to {new_plan.name} ({new_period}).')
            except Plan.DoesNotExist:
                messages.error(request, 'Plan not found.')

    elif action == 'suspend':
        sub.status = 'suspended'
        sub.save()
        BillingEvent.objects.create(
            user=sub.user,
            event_type='cancel',
            plan=sub.plan,
            amount=0,
            note='Suspended by admin',
        )
        messages.success(request, f'Suspended subscription for {sub.user.username}.')

    elif action == 'reactivate':
        if sub.expires_at < timezone.now():
            sub.expires_at = timezone.now() + timedelta(days=_period_days(sub.billing_period))
        sub.status = 'active'
        sub.save()
        BillingEvent.objects.create(
            user=sub.user,
            event_type='renew',
            plan=sub.plan,
            amount=0,
            note='Reactivated by admin',
        )
        messages.success(request, f'Reactivated subscription for {sub.user.username}.')

    return redirect('subscriptions:admin_subscriptions')


@staff_member_required
def admin_update_discount(request):
    """Admin action to update yearly discount percentage for a plan."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_dashboard')

    plan_id = request.POST.get('plan_id')
    discount = request.POST.get('discount')

    try:
        plan = Plan.objects.get(pk=plan_id)
        plan.yearly_discount_percent = int(discount)
        plan.save(update_fields=['yearly_discount_percent'])
        messages.success(request, f'Updated {plan.name} yearly discount to {discount}%.')
    except (Plan.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Invalid plan or discount value.')

    return redirect('subscriptions:admin_plans')


@staff_member_required
def admin_mark_order_paid(request, order_id):
    """Admin action: mark a card order as paid (for physical/in-person sales). Does NOT activate subscription."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_dashboard')

    from cards.models import CardOrder

    order = get_object_or_404(CardOrder, pk=order_id)
    if order.status != 'pending':
        messages.info(request, f'Order #{order.pk} is already {order.get_status_display()}.')
        return redirect('subscriptions:admin_dashboard')

    order.status = 'paid'
    order.channel = 'admin'
    order.paid_at = timezone.now()
    order.save()

    messages.success(request, f'Order #{order.pk} marked as paid for {order.user.username}.')
    return redirect('subscriptions:admin_orders')


@staff_member_required
def admin_activate_subscription(request, order_id):
    """Admin action: activate monthly subscription for a card order (after card is delivered)."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_dashboard')

    from cards.models import CardOrder
    from cards.views import _activate_subscription_after_purchase

    order = get_object_or_404(CardOrder, pk=order_id)

    if order.status not in ('paid', 'shipped', 'delivered'):
        messages.error(request, f'Order #{order.pk} must be paid before activating subscription.')
        return redirect('subscriptions:admin_orders')

    if order.subscription_activated:
        messages.info(request, f'Subscription already activated for {order.user.username}.')
        return redirect('subscriptions:admin_orders')

    _activate_subscription_after_purchase(order.user, order)

    messages.success(request, f'Monthly subscription activated for {order.user.username}.')
    return redirect('subscriptions:admin_orders')


@staff_member_required
def admin_update_order(request, order_id):
    """Admin action: update card order status (shipped, delivered)."""
    if request.method != 'POST':
        return redirect('subscriptions:admin_dashboard')

    from cards.models import CardOrder

    order = get_object_or_404(CardOrder, pk=order_id)
    new_status = request.POST.get('status', '')

    valid_transitions = {
        'paid': ['shipped'],
        'shipped': ['delivered'],
    }

    allowed = valid_transitions.get(order.status, [])
    if new_status not in allowed:
        messages.error(request, f'Cannot change order from {order.get_status_display()} to {new_status}.')
        return redirect('subscriptions:admin_orders')

    order.status = new_status
    if new_status == 'shipped':
        order.shipped_at = timezone.now()
    elif new_status == 'delivered':
        order.delivered_at = timezone.now()
    order.save()
    messages.success(request, f'Order #{order.pk} marked as {order.get_status_display()}.')
    return redirect('subscriptions:admin_orders')


# ═══════════════════════════════════════════════════════════════════
#  BLOG MANAGEMENT DASHBOARD
# ═══════════════════════════════════════════════════════════════════

@staff_member_required
def admin_blog_list(request):
    """List all blog posts with filters and stats."""
    from core.models import BlogPost, BlogComment
    posts = BlogPost.objects.select_related('author').all()

    # Stats
    total_posts = posts.count()
    published_count = posts.filter(status='published').count()
    draft_count = posts.filter(status='draft').count()
    total_views = sum(p.views_count for p in posts)
    total_comments = BlogComment.objects.count()
    pending_comments = BlogComment.objects.filter(is_approved=False).count()

    # Filters
    status_filter = request.GET.get('status', '')
    category_filter = request.GET.get('category', '')
    search_q = request.GET.get('q', '')

    if status_filter:
        posts = posts.filter(status=status_filter)
    if category_filter:
        posts = posts.filter(category=category_filter)
    if search_q:
        posts = posts.filter(
            Q(title__icontains=search_q) | Q(excerpt__icontains=search_q)
        )

    ctx = {
        **_admin_ctx(request),
        'posts': posts,
        'total_posts': total_posts,
        'published_count': published_count,
        'draft_count': draft_count,
        'total_views': total_views,
        'total_comments': total_comments,
        'pending_comments': pending_comments,
        'status_filter': status_filter,
        'category_filter': category_filter,
        'search_q': search_q,
        'categories': BlogPost.CATEGORY_CHOICES,
    }
    return render(request, 'subscriptions/admin_blog_list.html', ctx)


@staff_member_required
def admin_blog_create(request):
    """Create a new blog post."""
    from core.models import BlogPost, BlogImage
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        category = request.POST.get('category', 'nfc')
        excerpt = request.POST.get('excerpt', '').strip()
        body = request.POST.get('body', '').strip()
        status = request.POST.get('status', 'draft')
        is_featured = request.POST.get('is_featured') == 'on'
        cover = request.FILES.get('cover_image')

        if not title or not body:
            messages.error(request, 'Title and body are required.')
            return render(request, 'subscriptions/admin_blog_form.html', {
                **_admin_ctx(request),
                'categories': BlogPost.CATEGORY_CHOICES,
                'form_data': request.POST,
                'editing': False,
            })

        post = BlogPost(
            title=title,
            category=category,
            excerpt=excerpt,
            body=body,
            status=status,
            is_featured=is_featured,
            author=request.user,
        )
        if cover:
            post.cover_image = cover
        if status == 'published':
            post.published_at = timezone.now()
        post.save()

        # Handle multiple image uploads
        images = request.FILES.getlist('blog_images')
        captions = request.POST.getlist('image_captions')
        for i, img_file in enumerate(images):
            caption = captions[i] if i < len(captions) else ''
            BlogImage.objects.create(post=post, image=img_file, caption=caption)

        messages.success(request, f'Blog post "{title}" created successfully.')
        return redirect('subscriptions:admin_blog_detail', post_id=post.pk)

    ctx = {
        **_admin_ctx(request),
        'categories': BlogPost.CATEGORY_CHOICES,
        'editing': False,
    }
    return render(request, 'subscriptions/admin_blog_form.html', ctx)


@staff_member_required
def admin_blog_edit(request, post_id):
    """Edit an existing blog post."""
    from django.shortcuts import get_object_or_404
    from core.models import BlogPost, BlogImage
    post = get_object_or_404(BlogPost, pk=post_id)

    if request.method == 'POST':
        post.title = request.POST.get('title', '').strip()
        post.category = request.POST.get('category', 'nfc')
        post.excerpt = request.POST.get('excerpt', '').strip()
        post.body = request.POST.get('body', '').strip()
        new_status = request.POST.get('status', 'draft')
        post.is_featured = request.POST.get('is_featured') == 'on'
        cover = request.FILES.get('cover_image')

        if not post.title or not post.body:
            messages.error(request, 'Title and body are required.')
            return render(request, 'subscriptions/admin_blog_form.html', {
                **_admin_ctx(request),
                'post': post,
                'categories': BlogPost.CATEGORY_CHOICES,
                'editing': True,
            })

        if cover:
            post.cover_image = cover

        if new_status == 'published' and post.status != 'published':
            post.published_at = timezone.now()
        post.status = new_status
        post.save()

        # Delete images marked for removal
        delete_ids = request.POST.getlist('delete_images')
        if delete_ids:
            post.images.filter(pk__in=delete_ids).delete()

        # Handle new image uploads
        images = request.FILES.getlist('blog_images')
        captions = request.POST.getlist('image_captions')
        for i, img_file in enumerate(images):
            caption = captions[i] if i < len(captions) else ''
            BlogImage.objects.create(post=post, image=img_file, caption=caption)

        messages.success(request, f'Blog post "{post.title}" updated.')
        return redirect('subscriptions:admin_blog_detail', post_id=post.pk)

    ctx = {
        **_admin_ctx(request),
        'post': post,
        'categories': BlogPost.CATEGORY_CHOICES,
        'editing': True,
    }
    return render(request, 'subscriptions/admin_blog_form.html', ctx)


@staff_member_required
def admin_blog_delete(request, post_id):
    """Delete a blog post."""
    from django.shortcuts import get_object_or_404
    from core.models import BlogPost
    if request.method == 'POST':
        post = get_object_or_404(BlogPost, pk=post_id)
        title = post.title
        post.delete()
        messages.success(request, f'Blog post "{title}" deleted.')
    return redirect('subscriptions:admin_blog_list')


@staff_member_required
def admin_blog_detail(request, post_id):
    """View blog post analytics and comments."""
    from django.shortcuts import get_object_or_404
    from core.models import BlogPost
    post = get_object_or_404(BlogPost, pk=post_id)
    comments = post.comments.all()
    approved_comments = comments.filter(is_approved=True).count()
    pending_comments_count = comments.filter(is_approved=False).count()

    ctx = {
        **_admin_ctx(request),
        'post': post,
        'comments': comments,
        'approved_comments': approved_comments,
        'pending_comments': pending_comments_count,
    }
    return render(request, 'subscriptions/admin_blog_detail.html', ctx)


@staff_member_required
def admin_blog_comments(request):
    """List all comments across all posts."""
    from core.models import BlogComment
    comments = BlogComment.objects.select_related('post').all()
    status_filter = request.GET.get('status', '')
    if status_filter == 'approved':
        comments = comments.filter(is_approved=True)
    elif status_filter == 'pending':
        comments = comments.filter(is_approved=False)

    ctx = {
        **_admin_ctx(request),
        'comments': comments,
        'status_filter': status_filter,
        'total_comments': BlogComment.objects.count(),
        'approved_count': BlogComment.objects.filter(is_approved=True).count(),
        'pending_count': BlogComment.objects.filter(is_approved=False).count(),
    }
    return render(request, 'subscriptions/admin_blog_comments.html', ctx)


@staff_member_required
def admin_blog_comment_action(request, comment_id):
    """Approve or delete a comment."""
    from django.shortcuts import get_object_or_404
    from core.models import BlogComment
    if request.method == 'POST':
        comment = get_object_or_404(BlogComment, pk=comment_id)
        action = request.POST.get('action', '')
        if action == 'approve':
            comment.is_approved = True
            comment.save()
            messages.success(request, 'Comment approved.')
        elif action == 'reject':
            comment.is_approved = False
            comment.save()
            messages.success(request, 'Comment rejected.')
        elif action == 'delete':
            comment.delete()
            messages.success(request, 'Comment deleted.')
        redirect_to = request.POST.get('next', '')
        if redirect_to:
            return redirect(redirect_to)
    return redirect('subscriptions:admin_blog_comments')


@staff_member_required
def admin_blog_toggle(request, post_id):
    """Quick toggle: publish/draft or featured."""
    from django.shortcuts import get_object_or_404
    from core.models import BlogPost
    if request.method == 'POST':
        post = get_object_or_404(BlogPost, pk=post_id)
        action = request.POST.get('action', '')
        if action == 'publish':
            post.status = 'published'
            if not post.published_at:
                post.published_at = timezone.now()
            post.save()
            messages.success(request, f'"{post.title}" published.')
        elif action == 'unpublish':
            post.status = 'draft'
            post.save()
            messages.success(request, f'"{post.title}" moved to draft.')
        elif action == 'feature':
            post.is_featured = not post.is_featured
            post.save()
            state = 'featured' if post.is_featured else 'unfeatured'
            messages.success(request, f'"{post.title}" {state}.')
    return redirect('subscriptions:admin_blog_list')


# ──────────────────────────────────────────────
# NFC Card URLs Management
# ──────────────────────────────────────────────

@staff_member_required
def admin_nfc_urls(request):
    """List all user profile NFC URLs for card configuration."""
    from profiles.models import Profile
    from django.db.models import Q

    search_q = request.GET.get('q', '').strip()
    profiles = Profile.objects.select_related('user').all().order_by('user__first_name', 'user__last_name')

    if search_q:
        profiles = profiles.filter(
            Q(user__first_name__icontains=search_q) |
            Q(user__last_name__icontains=search_q) |
            Q(user__username__icontains=search_q) |
            Q(user__email__icontains=search_q) |
            Q(profile_code__icontains=search_q) |
            Q(display_name__icontains=search_q)
        )

    total_profiles = Profile.objects.count()
    with_names = Profile.objects.exclude(
        Q(user__first_name='') | Q(user__last_name='')
    ).count()
    missing_names = total_profiles - with_names

    ctx = {
        **_admin_ctx(request),
        'profiles': profiles,
        'search_q': search_q,
        'total_profiles': total_profiles,
        'with_names': with_names,
        'missing_names': missing_names,
        'debug': django_settings.DEBUG,
    }
    return render(request, 'subscriptions/admin_nfc_urls.html', ctx)


# ──────────────────────────────────────────────
# Revenue Analytics
# ──────────────────────────────────────────────

@staff_member_required
def admin_analytics(request):
    """Revenue analytics dashboard with monthly/yearly breakdowns."""
    from django.contrib.auth import get_user_model
    from cards.models import CardOrder
    from companies.models import BulkCardOrder, CompanyBillingEvent

    now = timezone.now()
    User = get_user_model()

    # ── Period filter (default: last 12 months) ──
    period_filter = request.GET.get('period', '12m')
    period_map = {
        '30d': 30, '90d': 90, '6m': 180, '12m': 365, 'all': None,
    }
    days_back = period_map.get(period_filter, 365)
    if days_back:
        date_from = now - timedelta(days=days_back)
    else:
        date_from = None

    # ── Helper to filter by date range ──
    def _date_filter(qs, field='created_at'):
        if date_from:
            return qs.filter(**{f'{field}__gte': date_from})
        return qs

    # ── Total Revenue (all time) ──
    total_sub_revenue = BillingEvent.objects.filter(
        event_type__in=('subscribe', 'upgrade', 'renew', 'downgrade'), amount__gt=0,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    total_company_sub_revenue = CompanyBillingEvent.objects.filter(
        event_type__in=('subscribe', 'upgrade', 'renew', 'downgrade'), amount__gt=0,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    total_card_revenue = CardOrder.objects.filter(
        status__in=('paid', 'shipped', 'delivered'),
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    total_bulk_revenue = BulkCardOrder.objects.filter(
        status__in=('paid', 'processing', 'shipped', 'delivered'),
    ).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')

    total_revenue_all = total_sub_revenue + total_company_sub_revenue + total_card_revenue + total_bulk_revenue

    # ── Filtered Period Revenue ──
    period_sub = _date_filter(BillingEvent.objects.filter(
        event_type__in=('subscribe', 'upgrade', 'renew', 'downgrade'), amount__gt=0,
    )).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    period_company_sub = _date_filter(CompanyBillingEvent.objects.filter(
        event_type__in=('subscribe', 'upgrade', 'renew', 'downgrade'), amount__gt=0,
    )).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    period_card = _date_filter(CardOrder.objects.filter(
        status__in=('paid', 'shipped', 'delivered'),
    )).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    period_bulk = _date_filter(BulkCardOrder.objects.filter(
        status__in=('paid', 'processing', 'shipped', 'delivered'),
    )).aggregate(t=Sum('total_amount'))['t'] or Decimal('0')

    period_total = period_sub + period_company_sub + period_card + period_bulk
    period_subscription_total = period_sub + period_company_sub
    period_cards_total = period_card + period_bulk

    # ── Monthly Revenue Breakdown (last 12 months for chart) ──
    from django.db.models.functions import TruncMonth
    chart_months = 12
    chart_from = (now - timedelta(days=chart_months * 31)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Personal subscription revenue by month
    sub_by_month = dict(
        BillingEvent.objects.filter(
            event_type__in=('subscribe', 'upgrade', 'renew', 'downgrade'),
            amount__gt=0, created_at__gte=chart_from,
        ).annotate(month=TruncMonth('created_at')).values('month').annotate(
            total=Sum('amount'),
        ).values_list('month', 'total')
    )

    # Company subscription revenue by month
    co_sub_by_month = dict(
        CompanyBillingEvent.objects.filter(
            event_type__in=('subscribe', 'upgrade', 'renew', 'downgrade'),
            amount__gt=0, created_at__gte=chart_from,
        ).annotate(month=TruncMonth('created_at')).values('month').annotate(
            total=Sum('amount'),
        ).values_list('month', 'total')
    )

    # Card order revenue by month
    card_by_month = dict(
        CardOrder.objects.filter(
            status__in=('paid', 'shipped', 'delivered'), created_at__gte=chart_from,
        ).annotate(month=TruncMonth('created_at')).values('month').annotate(
            total=Sum('amount'),
        ).values_list('month', 'total')
    )

    # Bulk order revenue by month
    bulk_by_month = dict(
        BulkCardOrder.objects.filter(
            status__in=('paid', 'processing', 'shipped', 'delivered'), created_at__gte=chart_from,
        ).annotate(month=TruncMonth('created_at')).values('month').annotate(
            total=Sum('total_amount'),
        ).values_list('month', 'total')
    )

    # Build chart data arrays
    chart_labels = []
    chart_sub_data = []
    chart_card_data = []
    chart_total_data = []
    for i in range(chart_months):
        dt = (now - timedelta(days=(chart_months - 1 - i) * 30)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Use timezone-aware datetime
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        label = dt.strftime('%b %Y')
        sub_val = float(sub_by_month.get(dt, 0) or 0) + float(co_sub_by_month.get(dt, 0) or 0)
        card_val = float(card_by_month.get(dt, 0) or 0) + float(bulk_by_month.get(dt, 0) or 0)
        chart_labels.append(label)
        chart_sub_data.append(round(sub_val, 2))
        chart_card_data.append(round(card_val, 2))
        chart_total_data.append(round(sub_val + card_val, 2))

    # ── Recent Transactions ──
    recent_billing = list(BillingEvent.objects.select_related('user', 'plan').filter(
        amount__gt=0,
    ).order_by('-created_at')[:10])

    recent_card_orders = list(CardOrder.objects.select_related('user', 'card_product').filter(
        status__in=('paid', 'shipped', 'delivered'),
    ).order_by('-created_at')[:10])

    # Merge and sort
    recent_transactions = []
    for e in recent_billing:
        recent_transactions.append({
            'date': e.created_at,
            'type': 'Subscription',
            'description': f'{e.get_event_type_display()} — {e.plan.name if e.plan else "N/A"}',
            'customer': e.user.get_full_name() or e.user.username,
            'amount': e.amount,
        })
    for o in recent_card_orders:
        recent_transactions.append({
            'date': o.created_at,
            'type': 'Card Order',
            'description': o.card_product.name,
            'customer': o.user.get_full_name() or o.user.username,
            'amount': o.amount,
        })
    recent_transactions.sort(key=lambda x: x['date'], reverse=True)
    recent_transactions = recent_transactions[:15]

    # ── Subscription breakdown by plan ──
    plan_breakdown = list(
        Subscription.objects.filter(status='active', expires_at__gt=now).values(
            'plan__name', 'plan__price',
        ).annotate(count=Count('id')).order_by('-count')
    )

    # ── Key metrics ──
    active_subs = Subscription.objects.filter(status='active', expires_at__gt=now).count()
    total_users = User.objects.count()
    total_orders = CardOrder.objects.filter(status__in=('paid', 'shipped', 'delivered')).count()
    total_orders += BulkCardOrder.objects.filter(status__in=('paid', 'processing', 'shipped', 'delivered')).count()

    # MRR estimate (Monthly Recurring Revenue)
    from django.db.models import F
    mrr_personal = Subscription.objects.filter(
        status='active', expires_at__gt=now, billing_period='monthly',
    ).aggregate(t=Sum('plan__price'))['t'] or Decimal('0')
    mrr_yearly = Subscription.objects.filter(
        status='active', expires_at__gt=now, billing_period='yearly',
    ).select_related('plan').values_list('plan__price', 'plan__yearly_discount_percent')
    mrr_from_yearly = Decimal('0')
    for price, discount in mrr_yearly:
        monthly_equiv = price * (Decimal(1) - Decimal(discount) / Decimal(100))
        mrr_from_yearly += monthly_equiv
    mrr = mrr_personal + mrr_from_yearly

    # ARR
    arr = mrr * 12

    ctx = {
        **_admin_ctx(request),
        'period_filter': period_filter,
        # Totals (all time)
        'total_revenue_all': total_revenue_all,
        'total_sub_revenue': total_sub_revenue + total_company_sub_revenue,
        'total_card_revenue': total_card_revenue + total_bulk_revenue,
        # Period totals
        'period_total': period_total,
        'period_subscription_total': period_subscription_total,
        'period_cards_total': period_cards_total,
        'period_sub': period_sub,
        'period_company_sub': period_company_sub,
        'period_card': period_card,
        'period_bulk': period_bulk,
        # Chart
        'chart_labels': json.dumps(chart_labels),
        'chart_sub_data': json.dumps(chart_sub_data),
        'chart_card_data': json.dumps(chart_card_data),
        'chart_total_data': json.dumps(chart_total_data),
        # Key metrics
        'mrr': mrr,
        'arr': arr,
        'active_subs': active_subs,
        'total_users': total_users,
        'total_orders': total_orders,
        # Breakdown
        'plan_breakdown': plan_breakdown,
        'recent_transactions': recent_transactions,
    }
    return render(request, 'subscriptions/admin_analytics.html', ctx)


@staff_member_required
def admin_card_pricing(request):
    """Manage NFC card product pricing and images."""
    from cards.models import NFCCardProduct
    products = NFCCardProduct.objects.prefetch_related('gallery_images').all().order_by('sort_order', 'price')
    ctx = {'products': products}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_card_pricing.html', ctx)


@staff_member_required
@require_POST
def admin_update_card_price(request, product_id):
    """Update price and availability for a card product."""
    from cards.models import NFCCardProduct
    product = get_object_or_404(NFCCardProduct, pk=product_id)

    price = request.POST.get('price')
    is_available = request.POST.get('is_available') == 'on'

    if price is not None:
        try:
            product.price = Decimal(price)
        except Exception:
            messages.error(request, 'Invalid price.')
            return redirect('subscriptions:admin_card_pricing')

    product.is_available = is_available
    product.save(update_fields=['price', 'is_available'])

    messages.success(request, f'{product.name} pricing updated successfully.')
    return redirect('subscriptions:admin_card_pricing')


@staff_member_required
@require_POST
def admin_upload_card_image(request, product_id):
    """Upload a gallery image for a card product."""
    from cards.models import NFCCardProduct, CardProductImage
    product = get_object_or_404(NFCCardProduct, pk=product_id)

    image_file = request.FILES.get('image')
    if not image_file:
        messages.error(request, 'No image file provided.')
        return redirect('subscriptions:admin_card_pricing')

    caption = request.POST.get('caption', '').strip()
    is_primary = request.POST.get('is_primary') == 'on'

    # If this is the first image, make it primary automatically
    if not product.gallery_images.exists():
        is_primary = True

    CardProductImage.objects.create(
        product=product,
        image=image_file,
        caption=caption,
        is_primary=is_primary,
    )

    messages.success(request, f'Image uploaded for {product.name}.')
    return redirect('subscriptions:admin_card_pricing')


@staff_member_required
@require_POST
def admin_delete_card_image(request, image_id):
    """Delete a gallery image for a card product."""
    from cards.models import CardProductImage
    img = get_object_or_404(CardProductImage, pk=image_id)
    product_name = img.product.name
    was_primary = img.is_primary
    product = img.product
    img.image.delete(save=False)
    img.delete()

    # If deleted image was primary, promote the next one
    if was_primary:
        next_img = product.gallery_images.first()
        if next_img:
            next_img.is_primary = True
            next_img.save(update_fields=['is_primary'])

    messages.success(request, f'Image removed from {product_name}.')
    return redirect('subscriptions:admin_card_pricing')


@staff_member_required
@require_POST
def admin_set_primary_card_image(request, image_id):
    """Set a gallery image as the primary image for its product."""
    from cards.models import CardProductImage
    img = get_object_or_404(CardProductImage, pk=image_id)
    img.is_primary = True
    img.save()  # save() method handles unsetting previous primary
    messages.success(request, f'Primary image updated for {img.product.name}.')
    return redirect('subscriptions:admin_card_pricing')


@staff_member_required
def admin_payment_methods(request):
    """Manage payment method availability (enable/disable)."""
    from .models import PaymentMethodSettings
    
    # Initialize default payment methods if they don't exist
    default_methods = [
        {'method': 'paypal', 'display_name': 'PayPal', 'description': 'PayPal recurring subscriptions and one-time payments'},
        {'method': 'bank_transfer', 'display_name': 'Bank Transfer', 'description': 'Direct bank transfer with proof of payment upload'},
        {'method': 'ecocash', 'display_name': 'EcoCash', 'description': 'Mobile money payment via EcoCash'},
        {'method': 'cash', 'display_name': 'Cash Payment', 'description': 'Pay with cash on delivery or in-person, requires admin approval'},
    ]
    
    for method_data in default_methods:
        PaymentMethodSettings.objects.get_or_create(
            method=method_data['method'],
            defaults={
                'display_name': method_data['display_name'],
                'description': method_data['description'],
                'is_enabled': True,
            }
        )
    
    methods = PaymentMethodSettings.objects.all().order_by('method')
    
    ctx = {
        'methods': methods,
    }
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_payment_methods.html', ctx)


@staff_member_required
@require_POST
def admin_toggle_payment_method(request, method_id):
    """Toggle a payment method on/off."""
    from .models import PaymentMethodSettings
    
    method_setting = get_object_or_404(PaymentMethodSettings, pk=method_id)
    method_setting.is_enabled = not method_setting.is_enabled
    method_setting.save()
    
    status = 'enabled' if method_setting.is_enabled else 'disabled'
    messages.success(request, f'{method_setting.display_name} has been {status}.')
    
    return redirect('subscriptions:admin_payment_methods')


# ── Banking Details Management ──

@staff_member_required
def admin_banking_details(request):
    """List and add banking details."""
    from .models import BankingDetail

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            BankingDetail.objects.create(
                bank_name=request.POST.get('bank_name', '').strip(),
                account_name=request.POST.get('account_name', '').strip(),
                account_number=request.POST.get('account_number', '').strip(),
                branch=request.POST.get('branch', '').strip(),
                branch_code=request.POST.get('branch_code', '').strip(),
                swift_code=request.POST.get('swift_code', '').strip(),
                currency=request.POST.get('currency', 'USD').strip(),
                is_active=request.POST.get('is_active') == 'on',
                is_primary=request.POST.get('is_primary') == 'on',
                notes=request.POST.get('notes', '').strip(),
            )
            messages.success(request, 'Bank account added successfully.')
            return redirect('subscriptions:admin_banking_details')

    accounts = BankingDetail.objects.all()
    ctx = {'accounts': accounts}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_banking_details.html', ctx)


@staff_member_required
def admin_edit_banking_detail(request, pk):
    """Edit an existing bank account."""
    from .models import BankingDetail
    account = get_object_or_404(BankingDetail, pk=pk)

    if request.method == 'POST':
        account.bank_name = request.POST.get('bank_name', '').strip()
        account.account_name = request.POST.get('account_name', '').strip()
        account.account_number = request.POST.get('account_number', '').strip()
        account.branch = request.POST.get('branch', '').strip()
        account.branch_code = request.POST.get('branch_code', '').strip()
        account.swift_code = request.POST.get('swift_code', '').strip()
        account.currency = request.POST.get('currency', 'USD').strip()
        account.is_active = request.POST.get('is_active') == 'on'
        account.is_primary = request.POST.get('is_primary') == 'on'
        account.notes = request.POST.get('notes', '').strip()
        account.save()
        messages.success(request, f'"{account.bank_name}" updated successfully.')
        return redirect('subscriptions:admin_banking_details')

    ctx = {'account': account}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_banking_detail_edit.html', ctx)


@staff_member_required
@require_POST
def admin_delete_banking_detail(request, pk):
    """Delete a bank account."""
    from .models import BankingDetail
    account = get_object_or_404(BankingDetail, pk=pk)
    name = account.bank_name
    account.delete()
    messages.success(request, f'"{name}" bank account deleted.')
    return redirect('subscriptions:admin_banking_details')


# ═══════════════════════════════════════════════════════════════════
#  VIDEO TESTIMONIALS MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

@staff_member_required
def admin_video_testimonials(request):
    """List and manage video testimonials."""
    from core.models import VideoTestimonial
    testimonials = VideoTestimonial.objects.all()
    active_count = testimonials.filter(is_active=True).count()
    total = testimonials.count()
    ctx = {
        'testimonials': testimonials,
        'active_count': active_count,
        'total_count': total,
        'inactive_count': total - active_count,
    }
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_video_testimonials.html', ctx)


@staff_member_required
def admin_video_testimonial_create(request):
    """Create a new video testimonial."""
    from core.models import VideoTestimonial
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        review = request.POST.get('review', '').strip()
        rating = int(request.POST.get('rating', 5))
        date_label = request.POST.get('date_label', '').strip()
        video_source = request.POST.get('video_source', 'upload')
        video_url = request.POST.get('video_url', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        is_verified = request.POST.get('is_verified') == 'on'
        sort_order = int(request.POST.get('sort_order', 0))

        if not name or not review:
            messages.error(request, 'Name and review are required.')
            ctx = {'mode': 'create'}
            ctx.update(_admin_ctx(request))
            return render(request, 'subscriptions/admin_video_testimonial_form.html', ctx)

        testimonial = VideoTestimonial(
            name=name, review=review, rating=rating, date_label=date_label,
            video_source=video_source, video_url=video_url,
            is_active=is_active, is_verified=is_verified, sort_order=sort_order,
        )

        if 'thumbnail' in request.FILES:
            testimonial.thumbnail = request.FILES['thumbnail']

        if video_source == 'upload' and 'video_file' in request.FILES:
            testimonial.video_file = request.FILES['video_file']

        testimonial.save()
        messages.success(request, f'Testimonial from "{name}" created.')
        return redirect('subscriptions:admin_video_testimonials')

    ctx = {'mode': 'create'}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_video_testimonial_form.html', ctx)


@staff_member_required
def admin_video_testimonial_edit(request, pk):
    """Edit an existing video testimonial."""
    from core.models import VideoTestimonial
    testimonial = get_object_or_404(VideoTestimonial, pk=pk)

    if request.method == 'POST':
        testimonial.name = request.POST.get('name', '').strip()
        testimonial.review = request.POST.get('review', '').strip()
        testimonial.rating = int(request.POST.get('rating', 5))
        testimonial.date_label = request.POST.get('date_label', '').strip()
        testimonial.video_source = request.POST.get('video_source', 'upload')
        testimonial.video_url = request.POST.get('video_url', '').strip()
        testimonial.is_active = request.POST.get('is_active') == 'on'
        testimonial.is_verified = request.POST.get('is_verified') == 'on'
        testimonial.sort_order = int(request.POST.get('sort_order', 0))

        if not testimonial.name or not testimonial.review:
            messages.error(request, 'Name and review are required.')
            ctx = {'mode': 'edit', 'testimonial': testimonial}
            ctx.update(_admin_ctx(request))
            return render(request, 'subscriptions/admin_video_testimonial_form.html', ctx)

        if 'thumbnail' in request.FILES:
            testimonial.thumbnail = request.FILES['thumbnail']

        if testimonial.video_source == 'upload' and 'video_file' in request.FILES:
            testimonial.video_file = request.FILES['video_file']

        testimonial.save()
        messages.success(request, f'Testimonial from "{testimonial.name}" updated.')
        return redirect('subscriptions:admin_video_testimonials')

    ctx = {'mode': 'edit', 'testimonial': testimonial}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_video_testimonial_form.html', ctx)


@staff_member_required
@require_POST
def admin_video_testimonial_delete(request, pk):
    """Delete a video testimonial."""
    from core.models import VideoTestimonial
    testimonial = get_object_or_404(VideoTestimonial, pk=pk)
    name = testimonial.name
    testimonial.delete()
    messages.success(request, f'Testimonial from "{name}" deleted.')
    return redirect('subscriptions:admin_video_testimonials')


@staff_member_required
@require_POST
def admin_video_testimonial_toggle(request, pk):
    """Toggle active status of a video testimonial."""
    from core.models import VideoTestimonial
    testimonial = get_object_or_404(VideoTestimonial, pk=pk)
    testimonial.is_active = not testimonial.is_active
    testimonial.save(update_fields=['is_active'])
    status = 'activated' if testimonial.is_active else 'deactivated'
    messages.success(request, f'Testimonial from "{testimonial.name}" {status}.')
    return redirect('subscriptions:admin_video_testimonials')


# ═══════════════════════════════════════════════════════════════════
#  PARTNER LOGOS
# ═══════════════════════════════════════════════════════════════════

@staff_member_required
def admin_partner_logos(request):
    """List and manage partner logos."""
    from core.models import PartnerLogo
    logos = PartnerLogo.objects.all()
    total = logos.count()
    active_count = logos.filter(is_active=True).count()
    ctx = {
        'logos': logos,
        'total': total,
        'active_count': active_count,
        'inactive_count': total - active_count,
    }
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_partner_logos.html', ctx)


@staff_member_required
def admin_partner_logo_create(request):
    """Create a new partner logo."""
    from core.models import PartnerLogo
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        website_url = request.POST.get('website_url', '').strip()
        sort_order = request.POST.get('sort_order', 0)
        is_active = request.POST.get('is_active') == 'on'
        logo_file = request.FILES.get('logo')

        if not name or not logo_file:
            messages.error(request, 'Name and logo image are required.')
            ctx = {'mode': 'create'}
            ctx.update(_admin_ctx(request))
            return render(request, 'subscriptions/admin_partner_logo_form.html', ctx)

        PartnerLogo.objects.create(
            name=name,
            logo=logo_file,
            website_url=website_url,
            sort_order=int(sort_order) if sort_order else 0,
            is_active=is_active,
        )
        messages.success(request, f'Partner logo "{name}" created.')
        return redirect('subscriptions:admin_partner_logos')

    ctx = {'mode': 'create'}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_partner_logo_form.html', ctx)


@staff_member_required
def admin_partner_logo_edit(request, pk):
    """Edit an existing partner logo."""
    from core.models import PartnerLogo
    logo_obj = get_object_or_404(PartnerLogo, pk=pk)

    if request.method == 'POST':
        logo_obj.name = request.POST.get('name', '').strip()
        logo_obj.website_url = request.POST.get('website_url', '').strip()
        sort_order = request.POST.get('sort_order', 0)
        logo_obj.sort_order = int(sort_order) if sort_order else 0
        logo_obj.is_active = request.POST.get('is_active') == 'on'

        new_logo = request.FILES.get('logo')
        if new_logo:
            logo_obj.logo = new_logo

        logo_obj.save()
        messages.success(request, f'Partner logo "{logo_obj.name}" updated.')
        return redirect('subscriptions:admin_partner_logos')

    ctx = {'mode': 'edit', 'logo_obj': logo_obj}
    ctx.update(_admin_ctx(request))
    return render(request, 'subscriptions/admin_partner_logo_form.html', ctx)


@staff_member_required
@require_POST
def admin_partner_logo_delete(request, pk):
    """Delete a partner logo."""
    from core.models import PartnerLogo
    logo_obj = get_object_or_404(PartnerLogo, pk=pk)
    name = logo_obj.name
    logo_obj.delete()
    messages.success(request, f'Partner logo "{name}" deleted.')
    return redirect('subscriptions:admin_partner_logos')


@staff_member_required
@require_POST
def admin_partner_logo_toggle(request, pk):
    """Toggle active status of a partner logo."""
    from core.models import PartnerLogo
    logo_obj = get_object_or_404(PartnerLogo, pk=pk)
    logo_obj.is_active = not logo_obj.is_active
    logo_obj.save(update_fields=['is_active'])
    status = 'activated' if logo_obj.is_active else 'deactivated'
    messages.success(request, f'Partner logo "{logo_obj.name}" {status}.')
    return redirect('subscriptions:admin_partner_logos')
