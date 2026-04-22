import json
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .models import NFCCard, NFCCardProduct, CardOrder, PersonalProofOfPayment
from .forms import CheckoutAddressForm
from analytics.models import TapEvent
from subscriptions.models import Plan, Subscription, BillingEvent, BankingDetail
from subscriptions.middleware import check_user_subscription
from subscriptions import paypal as paypal_api

logger = logging.getLogger(__name__)


def _get_bank_details():
    """Get primary bank account as dict (backward-compatible with settings.BANK_DETAILS)."""
    primary = BankingDetail.get_primary()
    return primary.as_dict() if primary else {}


def _get_bank_accounts():
    """Get all active bank accounts."""
    return BankingDetail.get_active()


# ──────────────────────────────────────────────
#  Card Shop
# ──────────────────────────────────────────────

def card_shop(request):
    """Public page listing all available NFC card products."""
    products = NFCCardProduct.objects.filter(is_available=True).prefetch_related('gallery_images')
    
    # Authenticated users see the checkout-ready shop
    if request.user.is_authenticated:
        return render(request, 'cards/shop.html', {'products': products})
    
    # Unauthenticated users see the marketing/signup-focused shop
    return render(request, 'pages/home/shop_public.html', {'products': products})


@ensure_csrf_cookie
def ecommerce_store(request):
    """Full ecommerce store showcasing all available NFC card products."""
    products = NFCCardProduct.objects.filter(is_available=True).prefetch_related('gallery_images')
    cart_info = _cart_summary(request)

    context = {
        'products': products,
        'cart_json': json.dumps(cart_info),
        'page_title': 'NFC Business Cards Shop',
        'page_description': 'Discover innovative NFC-enabled business cards. Professional, modern, and interactive.',
    }

    return render(request, 'cards/ecommerce_store.html', context)


@login_required
def buy_card(request, slug):
    """Show checkout form (GET) or create PayPal order and redirect (POST)."""
    from decimal import Decimal
    from companies.models import CompanyMembership
    # Gate: company members cannot purchase cards individually
    if CompanyMembership.objects.filter(user=request.user, is_active=True).exists():
        messages.info(request, 'Card purchases are managed by your company.')
        return redirect('profiles:dashboard')

    product = get_object_or_404(NFCCardProduct, slug=slug, is_available=True)

    # Get enabled payment methods
    from subscriptions.models import PaymentMethodSettings
    enabled_payment_methods = PaymentMethodSettings.get_enabled_methods()
    
    # Filter payment methods based on user's country
    # Zimbabwe users (ZW) can use all methods, others only PayPal
    if request.user.country != 'ZW':
        enabled_payment_methods = [m for m in enabled_payment_methods if m == 'paypal']

    ctx = {
        'product': product,
        'bank_details': _get_bank_details(),
        'bank_accounts': _get_bank_accounts(),
        'enabled_payment_methods': enabled_payment_methods,
    }

    if request.method == 'GET':
        form = CheckoutAddressForm(user=request.user)
        ctx['form'] = form
        return render(request, 'cards/checkout.html', ctx)

    # POST — validate address, create order, route by payment method
    form = CheckoutAddressForm(request.POST, user=request.user)
    if not form.is_valid():
        ctx['form'] = form
        return render(request, 'cards/checkout.html', ctx)

    # Personal users always get InfinityCard branding at standard price
    total = product.price

    payment_method = request.POST.get('payment_method', 'paypal')
    if payment_method not in ('paypal', 'bank_transfer', 'ecocash', 'cash'):
        payment_method = 'paypal'

    # Prevent duplicate cash payments: block if user has a pending cash order
    if payment_method == 'cash':
        pending_cash = CardOrder.objects.filter(
            user=request.user, payment_method='cash', status='pending'
        ).first()
        if pending_cash:
            messages.error(
                request,
                f'You already have a pending cash payment (Order #{pending_cash.pk}). '
                f'Please wait for it to be approved or declined before placing a new order.'
            )
            return redirect('cards:buy_card', slug=product.slug)

    # Create local order with shipping address
    order = CardOrder(
        user=request.user,
        card_product=product,
        amount=total,
        channel='online',
        design_option='standard',
        payment_method=payment_method,
    )
    # Copy form fields to order
    for field_name in form.cleaned_data:
        setattr(order, field_name, form.cleaned_data[field_name])
    order.save()

    # ── 1. Cash Payment → No POP required, just pending for admin approval ──
    if payment_method == 'cash':
        logger.info('Card order #%s created with cash payment. Awaiting admin approval.', order.pk)
        messages.success(
            request,
            f'Order #{order.pk} created! Your order is pending. '
            f'Please pay in cash and an admin will approve your order once payment is received.'
        )
        return redirect('subscriptions:billing')

    # ── 2. Bank Transfer → POP upload page ──
    if payment_method == 'bank_transfer':
        logger.info('Card order #%s created with bank_transfer. Awaiting POP upload.', order.pk)
        messages.success(
            request,
            f'Order #{order.pk} created! Please upload your proof of payment to complete the purchase.'
        )
        return redirect('cards:upload_pop', pk=order.pk)

    # ── 2. EcoCash ──
    if payment_method == 'ecocash':
        ecocash_phone = request.POST.get('ecocash_phone', '').strip()
        if not ecocash_phone:
            order.delete()
            messages.error(request, 'Please enter your EcoCash phone number.')
            return redirect('cards:buy_card', slug=product.slug)

        order.ecocash_phone = ecocash_phone
        order.save(update_fields=['ecocash_phone'])

        # PRODUCTION: redirect to POP upload for now (until EcoCash API is integrated)
        messages.info(
            request,
            f'EcoCash payment initiated to {ecocash_phone}. '
            f'Please upload your proof of payment to complete the purchase.'
        )
        return redirect('cards:upload_pop', pk=order.pk)

    # ── 3. PayPal ──
    # Build description and redirect to PayPal
    desc = f'InfinityCard NFC Card - {product.name}'

    return_url = request.build_absolute_uri(
        reverse('cards:purchase_return') + f'?order_id={order.pk}'
    )
    cancel_url = request.build_absolute_uri(
        reverse('cards:purchase_cancel') + f'?order_id={order.pk}'
    )

    try:
        logger.info('Creating PayPal order: amount=%s, return=%s, cancel=%s', total, return_url, cancel_url)
        pp_order_id, approval_url = paypal_api.create_order(
            amount=total,
            description=desc,
            return_url=return_url,
            cancel_url=cancel_url,
        )
    except Exception as e:
        import traceback
        logger.error('PayPal create order failed: %s\n%s', e, traceback.format_exc())
        order.status = 'cancelled'
        order.save()
        messages.error(request, f'Unable to connect to PayPal: {e}')
        return redirect('cards:shop')

    if not approval_url:
        order.status = 'cancelled'
        order.save()
        messages.error(request, 'PayPal did not return a payment URL. Please try again.')
        return redirect('cards:shop')

    order.paypal_order_id = pp_order_id
    order.save()

    return redirect(approval_url)


@login_required
def purchase_return(request):
    """PayPal redirects here after user approves the one-time payment."""
    order_id = request.GET.get('order_id', '')
    pp_token = request.GET.get('token', '')  # PayPal sends token param

    logger.info('Card purchase return: order_id=%s, token=%s, GET=%s', order_id, pp_token, dict(request.GET))

    if not order_id:
        messages.error(request, 'Missing order details.')
        return redirect('cards:shop')

    order = get_object_or_404(CardOrder, pk=order_id, user=request.user)

    if order.status == 'paid':
        messages.info(request, 'This order has already been processed.')
        return redirect('subscriptions:billing')

    # Capture the payment
    pp_order_id = order.paypal_order_id or pp_token
    if not pp_order_id:
        messages.error(request, 'Missing PayPal order reference.')
        return redirect('cards:shop')

    try:
        capture_data = paypal_api.capture_order(pp_order_id)
        capture_status = capture_data.get('status', '')
        logger.info('Card purchase capture status: %s for order %s', capture_status, order.pk)
    except Exception as e:
        logger.error('PayPal capture failed for card order %s: %s', order.pk, e)
        messages.error(request, 'Payment capture failed. Please contact support.')
        return redirect('cards:shop')

    if capture_status != 'COMPLETED':
        messages.warning(request, f'Payment status is "{capture_status}". Please contact support if it does not resolve.')
        return redirect('cards:shop')

    # Mark order as paid
    order.status = 'paid'
    order.paid_at = timezone.now()
    order.save()

    # Subscription is NOT activated here — the super-admin will activate it
    # once the physical card has been delivered to the user.

    messages.success(
        request,
        f'Payment successful! Your {order.card_product.name} card has been ordered. '
        f'Your monthly subscription will be activated once your card is shipped to you.'
    )
    return redirect('subscriptions:billing')


@login_required
def purchase_cancel(request):
    """User cancelled payment at PayPal."""
    order_id = request.GET.get('order_id', '')
    if order_id:
        try:
            order = CardOrder.objects.get(pk=order_id, user=request.user, status='pending')
            order.status = 'cancelled'
            order.save()
        except CardOrder.DoesNotExist:
            pass
    messages.info(request, 'Payment was cancelled. You can try again anytime.')
    return redirect('cards:shop')


@login_required
def upload_pop(request, pk):
    """Upload proof of payment for a bank transfer or EcoCash personal card order."""
    from datetime import date
    order = get_object_or_404(CardOrder, pk=pk, user=request.user, status='pending')

    if order.payment_method not in ('bank_transfer', 'ecocash', 'cash'):
        messages.error(request, 'This order does not require a proof of payment upload.')
        return redirect('subscriptions:billing')

    existing_pop = order.proof_of_payments.filter(status='pending').first()

    if request.method == 'POST':
        document = request.FILES.get('document')
        reference_number = request.POST.get('reference_number', '').strip()
        amount_paid = request.POST.get('amount_paid', '')
        payment_date = request.POST.get('payment_date', '')
        notes = request.POST.get('notes', '').strip()

        if not document:
            messages.error(request, 'Please upload a proof of payment document.')
            return redirect('cards:upload_pop', pk=order.pk)

        try:
            from decimal import Decimal
            amount_paid = Decimal(amount_paid)
        except Exception:
            messages.error(request, 'Please enter a valid payment amount.')
            return redirect('cards:upload_pop', pk=order.pk)

        try:
            payment_date = date.fromisoformat(payment_date)
        except (ValueError, TypeError):
            payment_date = date.today()

        PersonalProofOfPayment.objects.create(
            order=order,
            uploaded_by=request.user,
            payment_type=order.payment_method,
            document=document,
            reference_number=reference_number,
            amount_paid=amount_paid,
            payment_date=payment_date,
            notes=notes,
        )

        messages.success(
            request,
            'Proof of payment uploaded successfully! We will review it and activate your order within 24 hours.'
        )
        return redirect('subscriptions:billing')

    return render(request, 'cards/upload_pop.html', {
        'order': order,
        'existing_pop': existing_pop,
        'bank_details': _get_bank_details(),
        'bank_accounts': _get_bank_accounts(),
        'ecocash_details': settings.ECOCASH_DETAILS,
    })


def _activate_subscription_after_purchase(user, order):
    """
    After a card purchase is paid, activate the user's monthly subscription
    on the default (cheapest) plan if they don't already have an active one.
    """
    if order.subscription_activated:
        return

    # Use the cheapest plan as the starter plan
    starter_plan = Plan.objects.order_by('price').first()
    if not starter_plan:
        logger.error('No plans exist to activate subscription for user %s', user.username)
        return

    now = timezone.now()

    try:
        sub = user.subscription
        # If they already have an active subscription, skip
        if sub.is_active():
            order.subscription_activated = True
            order.save()
            return
        # Reactivate expired subscription
        sub.plan = starter_plan
        sub.status = 'active'
        sub.billing_period = 'monthly'
        sub.expires_at = now + timedelta(days=30)
        sub.save()
    except Subscription.DoesNotExist:
        sub = Subscription.objects.create(
            user=user,
            plan=starter_plan,
            status='active',
            billing_period='monthly',
            expires_at=now + timedelta(days=30),
        )

    BillingEvent.objects.create(
        user=user,
        event_type='subscribe',
        plan=starter_plan,
        amount=0,
        note=f'Monthly subscription activated after {order.card_product.name} card purchase',
    )

    order.subscription_activated = True
    order.save()

    logger.info('Activated monthly subscription for %s after card purchase #%s', user.username, order.pk)


# ──────────────────────────────────────────────
#  NFC Tap Redirect
# ──────────────────────────────────────────────

@ratelimit(key='ip', rate='30/m', method='GET', block=True)
def tap_redirect(request, card_uid):
    card = get_object_or_404(NFCCard, uid=card_uid)

    if not card.is_active or not card.profile:
        return render(request, 'cards/inactive.html', status=200)

    # Check subscription status (personal or company)
    info = check_user_subscription(card.profile.user)
    if not info['active']:
        return render(request, 'profiles/suspended.html', {
            'profile': card.profile,
            'reason': info['reason'],
            'is_company': info['is_company'],
            'owner_name': info['owner_name'],
        })

    TapEvent.objects.create(
        profile=card.profile,
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )

    if settings.DEBUG:
        # In dev, redirect to the local profile path
        return redirect(card.profile.get_absolute_url())
    return redirect(card.profile.production_nfc_url)


# ──────────────────────────────────────────────
#  Session-based Shopping Cart
# ──────────────────────────────────────────────

def _get_cart(request):
    """Return the cart dict from session: {slug: qty}."""
    return request.session.get('cart', {})


def _save_cart(request, cart):
    request.session['cart'] = cart
    request.session.modified = True


def _cart_summary(request):
    """Build a full cart summary with product details for JSON responses."""
    cart = _get_cart(request)
    if not cart:
        return {'items': [], 'count': 0, 'total': '0.00'}

    products = NFCCardProduct.objects.filter(slug__in=cart.keys(), is_available=True).prefetch_related('gallery_images')
    product_map = {p.slug: p for p in products}

    items = []
    total = Decimal('0.00')
    count = 0
    for slug, qty in cart.items():
        p = product_map.get(slug)
        if not p:
            continue
        line_total = p.price * qty
        total += line_total
        count += qty
        # Use primary gallery image, fall back to legacy image field
        gallery_imgs = list(p.gallery_images.all())
        image_url = ''
        if gallery_imgs:
            image_url = gallery_imgs[0].image.url  # ordered by -is_primary, so first is primary
        elif p.image:
            image_url = p.image.url
        items.append({
            'slug': p.slug,
            'name': p.name,
            'material': p.get_material_display(),
            'price': str(p.price),
            'qty': qty,
            'line_total': str(line_total),
            'image': image_url,
        })

    return {'items': items, 'count': count, 'total': str(total)}


def cart_data(request):
    """GET endpoint returning cart contents as JSON."""
    return JsonResponse(_cart_summary(request))


@require_POST
def add_to_cart(request):
    """Add a product to the session cart. Expects JSON body with slug and optional qty."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = {}

    slug = body.get('slug', request.POST.get('slug', ''))
    qty = int(body.get('qty', request.POST.get('qty', 1)))
    if qty < 1:
        qty = 1

    product = NFCCardProduct.objects.filter(slug=slug, is_available=True).first()
    if not product:
        return JsonResponse({'error': 'Product not found'}, status=404)

    cart = _get_cart(request)
    cart[slug] = cart.get(slug, 0) + qty
    _save_cart(request, cart)

    summary = _cart_summary(request)
    # Use primary gallery image, fall back to legacy image field
    primary_img = product.gallery_images.first()
    added_image = primary_img.image.url if primary_img else (product.image.url if product.image else '')
    summary['added'] = {
        'slug': product.slug,
        'name': product.name,
        'price': str(product.price),
        'image': added_image,
    }
    return JsonResponse(summary)


@require_POST
def update_cart(request):
    """Update quantity for a product. qty=0 removes it."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = {}

    slug = body.get('slug', '')
    qty = int(body.get('qty', 0))

    cart = _get_cart(request)
    if qty <= 0:
        cart.pop(slug, None)
    else:
        if slug in cart or NFCCardProduct.objects.filter(slug=slug, is_available=True).exists():
            cart[slug] = qty
    _save_cart(request, cart)

    return JsonResponse(_cart_summary(request))


@require_POST
def remove_from_cart(request):
    """Remove a product entirely from the cart."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = {}

    slug = body.get('slug', '')
    cart = _get_cart(request)
    cart.pop(slug, None)
    _save_cart(request, cart)

    return JsonResponse(_cart_summary(request))


@require_POST
def clear_cart(request):
    """Empty the entire cart."""
    _save_cart(request, {})
    return JsonResponse(_cart_summary(request))
