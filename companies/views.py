import logging

from django.conf import settings as app_settings
from django.contrib import messages
from django.contrib.auth import login, get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from subscriptions import paypal as paypal_api
from subscriptions.models import BankingDetail
from subscriptions.billing_emails import send_company_subscription_confirmation, send_company_order_confirmation
from .forms import CompanyRegistrationForm, InviteEmployeeForm, EmployeeDetailForm, CompanySettingsForm
from .models import Company, CompanyMembership, BulkCardOrder, CardAssignment, CompanySubscription, CompanyBillingEvent, ProofOfPayment

User = get_user_model()

logger = logging.getLogger(__name__)


def _get_bank_details():
    """Get primary bank account as dict."""
    primary = BankingDetail.get_primary()
    return primary.as_dict() if primary else {}


def _get_bank_accounts():
    """Get all active bank accounts."""
    return BankingDetail.get_active()


# ── Helpers ──

def _get_admin_membership(user):
    """Return the CompanyMembership for this user if they are a company admin."""
    return CompanyMembership.objects.filter(
        user=user, role='admin', is_active=True
    ).select_related('company').first()


def company_admin_required(view_func):
    """Decorator: user must be logged in AND be a company admin."""
    @login_required
    def wrapper(request, *args, **kwargs):
        membership = _get_admin_membership(request.user)
        if not membership:
            messages.error(request, 'You do not have access to a company dashboard.')
            return redirect('profiles:dashboard')
        request.company = membership.company
        request.company_membership = membership
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


# ── Company Registration ──

@login_required
def register_company(request):
    """Register a new company. The current user becomes the admin."""
    # If already a company admin, redirect to dashboard
    existing = _get_admin_membership(request.user)
    if existing:
        return redirect('companies:dashboard')

    if request.method == 'POST':
        form = CompanyRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            company = form.save(commit=False)
            company.created_by = request.user
            company.save()
            # Create admin membership for this user
            CompanyMembership.objects.create(
                company=company,
                user=request.user,
                role='admin',
                invite_email=request.user.email,
                employee_name=request.user.get_full_name() or request.user.username,
            )
            messages.success(request, f'Company "{company.name}" created successfully!')
            return redirect('companies:dashboard')
    else:
        form = CompanyRegistrationForm()

    return render(request, 'companies/register.html', {'form': form})


# ── Company Dashboard ──

@company_admin_required
def dashboard(request):
    """Company admin main dashboard — overview of employees and orders."""
    company = request.company
    memberships = company.memberships.filter(is_active=True).select_related('user')
    orders = company.bulk_orders.all()[:5]

    stats = {
        'total_employees': memberships.count(),
        'pending_invites': memberships.filter(user__isnull=True).count(),
        'active_employees': memberships.filter(user__isnull=False).count(),
        'total_orders': company.bulk_orders.count(),
        'cards_assigned': company.card_assignments.exclude(status='unassigned').count(),
        'cards_unassigned': company.card_assignments.filter(status='unassigned').count(),
    }

    return render(request, 'companies/dashboard.html', {
        'company': company,
        'memberships': memberships,
        'recent_orders': orders,
        'stats': stats,
    })


# ── Employee Management ──

@company_admin_required
def employees(request):
    """List all employees in the company."""
    company = request.company
    memberships = company.memberships.filter(is_active=True).select_related('user').order_by('role', 'employee_name')

    return render(request, 'companies/employees.html', {
        'company': company,
        'memberships': memberships,
    })


@company_admin_required
def invite_employees(request):
    """Invite an employee by name and email."""
    company = request.company
    generated_links = []

    if request.method == 'POST':
        form = InviteEmployeeForm(request.POST)
        if form.is_valid():
            first_name = form.cleaned_data['first_name'].strip()
            last_name = form.cleaned_data['last_name'].strip()
            title = form.cleaned_data['title'].strip()
            email = form.cleaned_data['email']
            full_name = f'{first_name} {last_name}'

            membership, was_created = CompanyMembership.objects.get_or_create(
                company=company,
                invite_email=email,
                defaults={
                    'role': 'employee',
                    'employee_name': full_name,
                    'employee_title': title,
                },
            )
            if not was_created:
                # Update name/title if re-inviting an existing member
                updated_fields = []
                if not membership.employee_name:
                    membership.employee_name = full_name
                    updated_fields.append('employee_name')
                if not membership.employee_title:
                    membership.employee_title = title
                    updated_fields.append('employee_title')
                if updated_fields:
                    membership.save(update_fields=updated_fields)

            invite_url = request.build_absolute_uri(
                reverse('companies:accept_invite', args=[membership.invite_token])
            )
            generated_links.append({
                'name': full_name,
                'email': email,
                'url': invite_url,
                'new': was_created,
            })

            if was_created:
                messages.success(request, f'Invite created for {full_name}. Copy the link below to share.')
            else:
                messages.info(request, f'{email} was already invited — link shown below.')

            return render(request, 'companies/invite.html', {
                'company': company,
                'form': InviteEmployeeForm(),
                'generated_links': generated_links,
            })
    else:
        form = InviteEmployeeForm()

    return render(request, 'companies/invite.html', {
        'company': company,
        'form': form,
        'generated_links': generated_links,
    })


@company_admin_required
def edit_employee(request, pk):
    """Edit an employee's name, title, and role."""
    membership = get_object_or_404(CompanyMembership, pk=pk, company=request.company)

    if request.method == 'POST':
        form = EmployeeDetailForm(request.POST, instance=membership)
        if form.is_valid():
            form.save()
            messages.success(request, f'Updated {membership.employee_name or membership.invite_email}.')
            return redirect('companies:employees')
    else:
        form = EmployeeDetailForm(instance=membership)

    return render(request, 'companies/edit_employee.html', {
        'company': request.company,
        'membership': membership,
        'form': form,
    })


@company_admin_required
def remove_employee(request, pk):
    """Deactivate an employee membership."""
    membership = get_object_or_404(CompanyMembership, pk=pk, company=request.company)

    if request.method == 'POST':
        # Don't let admin remove themselves
        if membership.user == request.user:
            messages.error(request, 'You cannot remove yourself from the company.')
        else:
            membership.is_active = False
            membership.save(update_fields=['is_active'])
            messages.success(request, f'Removed {membership.employee_name or membership.invite_email}.')
        return redirect('companies:employees')

    return render(request, 'companies/confirm_remove.html', {
        'company': request.company,
        'membership': membership,
    })


# ── Invite Accept Flow ──

def accept_invite(request, token):
    """Public page: employee clicks invite link to join the company."""
    membership = get_object_or_404(CompanyMembership, invite_token=token, is_active=True)

    if membership.user is not None:
        messages.info(request, 'This invite has already been accepted.')
        return redirect('accounts:login')

    if request.user.is_authenticated:
        # Logged-in user accepts directly
        membership.accept(request.user)
        messages.success(request, f'Welcome to {membership.company.name}!')
        return redirect('profiles:dashboard')

    # Not logged in — show a page to sign up or log in
    return render(request, 'companies/accept_invite.html', {
        'membership': membership,
        'company': membership.company,
    })


def accept_invite_signup(request, token):
    """Handle signup for an invited employee."""
    from accounts.forms import SignupForm

    membership = get_object_or_404(CompanyMembership, invite_token=token, is_active=True)

    # Already accepted — redirect to login
    if membership.user is not None:
        messages.info(request, 'This invite has already been accepted. Please log in.')
        return redirect('accounts:login')

    if request.method == 'POST':
        data = request.POST.copy()
        data['email'] = membership.invite_email
        form = SignupForm(data)
        if form.is_valid():
            user = form.save()
            user.account_type = 'personal'
            user.save(update_fields=['account_type'])
            membership.accept(user)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome to {membership.company.name}! Now choose your profile type.')
            return redirect('accounts:choose_category')
    else:
        form = SignupForm(initial={'email': membership.invite_email})

    return render(request, 'companies/accept_signup.html', {
        'form': form,
        'membership': membership,
        'company': membership.company,
    })


# ── Order Cards (Catalog) ──

@company_admin_required
def order_cards(request):
    """Browse NFC card products and place a bulk order."""
    from cards.models import NFCCardProduct

    company = request.company
    products = NFCCardProduct.objects.filter(is_available=True)

    return render(request, 'companies/order_cards.html', {
        'company': company,
        'products': products,
    })


@company_admin_required
def order_cards_checkout(request, product_slug):
    """Checkout page for a specific card product — select quantity and design.
    POST creates the BulkCardOrder, then redirects to PayPal for payment."""
    from cards.models import NFCCardProduct
    from decimal import Decimal
    from subscriptions.models import PaymentMethodSettings

    company = request.company
    product = get_object_or_404(NFCCardProduct, slug=product_slug, is_available=True)
    employees = company.memberships.filter(is_active=True).select_related('user')
    
    # Get enabled payment methods and filter by country
    enabled_payment_methods = PaymentMethodSettings.get_enabled_methods()
    if request.user.country != 'ZW':
        enabled_payment_methods = [m for m in enabled_payment_methods if m == 'paypal']

    if request.method == 'POST':
        try:
            quantity = max(1, min(999, int(request.POST.get('quantity', 1))))
        except (ValueError, TypeError):
            quantity = 1
        design_option = request.POST.get('design_option', 'standard')
        design_notes = request.POST.get('design_notes', '')
        selected_members = request.POST.getlist('members')

        # Always charge standard price (custom designs are free)
        unit_price = product.price

        total = unit_price * quantity

        payment_method = request.POST.get('payment_method', 'paypal')
        if payment_method not in ('paypal', 'bank_transfer', 'ecocash', 'cash'):
            payment_method = 'paypal'

        # Prevent duplicate cash payments: block if company has a pending cash order
        if payment_method == 'cash':
            pending_cash = BulkCardOrder.objects.filter(
                company=company, payment_method='cash', status='pending'
            ).first()
            if pending_cash:
                messages.error(
                    request,
                    f'Your company already has a pending cash payment (Order #{pending_cash.pk}). '
                    f'Please wait for it to be approved or declined before placing a new order.'
                )
                return redirect('companies:order_checkout', product_slug=product.slug)

        # ── 1. Create the local order ──
        order = BulkCardOrder.objects.create(
            company=company,
            ordered_by=request.user,
            card_product=product,
            quantity=quantity,
            unit_price=unit_price,
            custom_design_fee=Decimal('0'),
            total_amount=total,
            design_option=design_option,
            design_notes=design_notes,
            payment_method=payment_method,
            shipping_company_name=company.name,
            shipping_contact_name=request.POST.get('contact_name', ''),
            shipping_email=request.POST.get('shipping_email', company.email or ''),
            shipping_phone=request.POST.get('shipping_phone', company.phone or ''),
            shipping_address1=request.POST.get('shipping_address1', ''),
            shipping_address2=request.POST.get('shipping_address2', ''),
            shipping_city=request.POST.get('shipping_city', ''),
            shipping_state=request.POST.get('shipping_state', ''),
            shipping_zip=request.POST.get('shipping_zip', ''),
            shipping_country=request.POST.get('shipping_country', 'United States'),
        )

        # Store selected members so we can create assignments after payment
        if selected_members:
            memberships_qs = CompanyMembership.objects.filter(
                pk__in=selected_members, company=company, is_active=True
            )
            order.members.set(memberships_qs)

        request.session[f'bulk_order_{order.pk}_members'] = selected_members

        # ── 2. Cash Payment → No POP required, just pending for admin approval ──
        if payment_method == 'cash':
            logger.info('Bulk order #%s created with cash payment. Awaiting admin approval.', order.pk)
            messages.success(
                request,
                f'Order #{order.pk} created! Your order is pending. '
                f'Please pay in cash and an admin will approve your order once payment is received.'
            )
            return redirect('companies:order_detail', pk=order.pk)

        # ── 3. Bank Transfer → POP upload page ──
        if payment_method == 'bank_transfer':
            logger.info('Bulk order #%s created with bank_transfer. Awaiting POP upload.', order.pk)
            messages.success(
                request,
                f'Order #{order.pk} created! Please upload your proof of payment to complete the purchase.'
            )
            return redirect('companies:upload_pop', pk=order.pk)

        # ── 2b. EcoCash → phone-based payment (auto-approve in dev mode) ──
        if payment_method == 'ecocash':
            ecocash_phone = request.POST.get('ecocash_phone', '').strip()
            if not ecocash_phone:
                order.delete()
                messages.error(request, 'Please enter your EcoCash phone number.')
                return redirect('companies:order_checkout', product_slug=product.slug)

            order.ecocash_phone = ecocash_phone
            order.save(update_fields=['ecocash_phone'])

            # PRODUCTION: Call EcoCash API here when available
            # For now, redirect to order detail with pending status
            messages.info(
                request,
                f'EcoCash payment initiated to {ecocash_phone}. '
                f'Please check your phone and enter your PIN to authorize the payment.'
            )
            return redirect('companies:order_detail', pk=order.pk)

        # ── 3. Process PayPal payment ──
        # Create PayPal order and redirect
        desc = f'{company.name} — {quantity}x {product.name}'
        if design_option == 'custom':
            desc += ' (Custom Branded)'

        return_url = request.build_absolute_uri(
            reverse('companies:payment_return') + f'?order_id={order.pk}'
        )
        cancel_url = request.build_absolute_uri(
            reverse('companies:payment_cancel') + f'?order_id={order.pk}'
        )

        try:
            logger.info('Creating PayPal order for bulk order #%s: $%s', order.pk, total)
            pp_order_id, approval_url = paypal_api.create_order(
                amount=total,
                description=desc,
                return_url=return_url,
                cancel_url=cancel_url,
            )
        except Exception as e:
            logger.error('PayPal create order failed for bulk #%s: %s', order.pk, e)
            order.status = 'cancelled'
            order.save()
            messages.error(request, f'Unable to connect to PayPal: {e}')
            return redirect('companies:order_cards')

        if not approval_url:
            order.status = 'cancelled'
            order.save()
            messages.error(request, 'PayPal did not return a payment URL. Please try again.')
            return redirect('companies:order_cards')

        order.paypal_order_id = pp_order_id
        order.save()

        return redirect(approval_url)

    return render(request, 'companies/order_checkout.html', {
        'company': company,
        'product': product,
        'employees': employees,
        'paypal_client_id': app_settings.PAYPAL_CLIENT_ID,
        'bank_details': _get_bank_details(),
        'bank_accounts': _get_bank_accounts(),
        'enabled_payment_methods': enabled_payment_methods,
    })


# ── Payment Callbacks ──

@company_admin_required
def payment_return(request):
    """PayPal redirects here after user approves the bulk order payment."""
    order_id = request.GET.get('order_id', '')
    pp_token = request.GET.get('token', '')

    logger.info('Bulk order payment return: order_id=%s, token=%s', order_id, pp_token)

    if not order_id:
        messages.error(request, 'Missing order details.')
        return redirect('companies:orders')

    company = request.company
    order = get_object_or_404(BulkCardOrder, pk=order_id, company=company)

    if order.status == 'paid':
        messages.info(request, 'This order has already been paid.')
        return redirect('companies:order_detail', pk=order.pk)

    # Capture the payment
    pp_order_id = order.paypal_order_id or pp_token
    if not pp_order_id:
        messages.error(request, 'Missing PayPal order reference.')
        return redirect('companies:orders')

    try:
        capture_data = paypal_api.capture_order(pp_order_id)
        capture_status = capture_data.get('status', '')
        logger.info('Bulk order capture status: %s for order #%s', capture_status, order.pk)
    except Exception as e:
        logger.error('PayPal capture failed for bulk order #%s: %s', order.pk, e)
        messages.error(request, 'Payment capture failed. Please contact support.')
        return redirect('companies:order_detail', pk=order.pk)

    if capture_status != 'COMPLETED':
        messages.warning(request, f'Payment status is "{capture_status}". Please contact support if it does not resolve.')
        return redirect('companies:order_detail', pk=order.pk)

    # ── Mark order as paid ──
    order.status = 'paid'
    order.paid_at = timezone.now()
    order.save(update_fields=['status', 'paid_at'])

    # ── Create card assignments now that payment is confirmed ──
    session_key = f'bulk_order_{order.pk}_members'
    selected_members = request.session.pop(session_key, [])

    if selected_members:
        memberships_qs = CompanyMembership.objects.filter(
            pk__in=selected_members, company=company, is_active=True
        )
        order.members.set(memberships_qs)
        for m in memberships_qs:
            CardAssignment.objects.create(
                company=company,
                membership=m,
                bulk_order=order,
                card_product=order.card_product,
                status='assigned',
                assigned_at=timezone.now(),
            )
        # If quantity > assigned members, create remaining as unassigned
        remaining = order.quantity - memberships_qs.count()
        for _ in range(max(0, remaining)):
            CardAssignment.objects.create(
                company=company,
                bulk_order=order,
                card_product=order.card_product,
                status='unassigned',
            )
    else:
        for _ in range(order.quantity):
            CardAssignment.objects.create(
                company=company,
                bulk_order=order,
                card_product=order.card_product,
                status='unassigned',
            )

    messages.success(
        request,
        f'Payment successful! Order #{order.pk} for {order.quantity} '
        f'{order.card_product.name} card(s) is confirmed. Total: ${order.total_amount}'
    )
    return redirect('companies:order_detail', pk=order.pk)


@company_admin_required
def payment_cancel(request):
    """User cancelled payment at PayPal."""
    order_id = request.GET.get('order_id', '')
    company = request.company

    if order_id:
        try:
            order = BulkCardOrder.objects.get(pk=order_id, company=company, status='pending')
            order.status = 'cancelled'
            order.save(update_fields=['status'])
            # Clean up session
            request.session.pop(f'bulk_order_{order.pk}_members', None)
            logger.info('Bulk order #%s cancelled by user', order.pk)
        except BulkCardOrder.DoesNotExist:
            pass

    messages.info(request, 'Payment was cancelled. You can try again anytime.')
    return redirect('companies:order_cards')


@company_admin_required
def upload_pop(request, pk):
    """Upload proof of payment for a bank transfer or EcoCash order."""
    from datetime import date
    company = request.company
    order = get_object_or_404(BulkCardOrder, pk=pk, company=company, status='pending')

    if order.payment_method not in ('bank_transfer', 'ecocash', 'cash'):
        messages.error(request, 'This order does not require a proof of payment upload.')
        return redirect('companies:order_detail', pk=order.pk)

    # Check if there's already a pending POP
    existing_pop = order.proof_of_payments.filter(status='pending').first()

    if request.method == 'POST':
        document = request.FILES.get('document')
        reference_number = request.POST.get('reference_number', '').strip()
        amount_paid = request.POST.get('amount_paid', '')
        payment_date = request.POST.get('payment_date', '')
        notes = request.POST.get('notes', '').strip()

        if not document:
            messages.error(request, 'Please upload a proof of payment document.')
            return redirect('companies:upload_pop', pk=order.pk)

        try:
            from decimal import Decimal
            amount_paid = Decimal(amount_paid)
        except Exception:
            messages.error(request, 'Please enter a valid payment amount.')
            return redirect('companies:upload_pop', pk=order.pk)

        try:
            payment_date = date.fromisoformat(payment_date)
        except (ValueError, TypeError):
            payment_date = date.today()

        ProofOfPayment.objects.create(
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
        return redirect('companies:order_detail', pk=order.pk)

    return render(request, 'companies/upload_pop.html', {
        'company': company,
        'order': order,
        'existing_pop': existing_pop,
        'bank_details': _get_bank_details(),
        'bank_accounts': _get_bank_accounts(),
        'ecocash_details': app_settings.ECOCASH_DETAILS,
    })


@company_admin_required
def retry_payment(request, pk):
    """Retry payment for a pending (unpaid) order."""
    company = request.company
    order = get_object_or_404(BulkCardOrder, pk=pk, company=company, status='pending')

    desc = f'{company.name} — {order.quantity}x {order.card_product.name}'
    if order.design_option == 'custom':
        desc += ' + Custom Design'

    return_url = request.build_absolute_uri(
        reverse('companies:payment_return') + f'?order_id={order.pk}'
    )
    cancel_url = request.build_absolute_uri(
        reverse('companies:payment_cancel') + f'?order_id={order.pk}'
    )

    try:
        logger.info('Retrying PayPal order for bulk #%s: $%s', order.pk, order.total_amount)
        pp_order_id, approval_url = paypal_api.create_order(
            amount=order.total_amount,
            description=desc,
            return_url=return_url,
            cancel_url=cancel_url,
        )
    except Exception as e:
        logger.error('PayPal retry failed for bulk #%s: %s', order.pk, e)
        messages.error(request, f'Unable to connect to PayPal: {e}')
        return redirect('companies:order_detail', pk=order.pk)

    if not approval_url:
        messages.error(request, 'PayPal did not return a payment URL. Please try again.')
        return redirect('companies:order_detail', pk=order.pk)

    order.paypal_order_id = pp_order_id
    order.save(update_fields=['paypal_order_id'])

    return redirect(approval_url)


# ── Orders List ──

@company_admin_required
def orders(request):
    """View all bulk card orders for this company."""
    company = request.company
    order_list = company.bulk_orders.select_related('card_product', 'ordered_by').all()

    return render(request, 'companies/orders.html', {
        'company': company,
        'orders': order_list,
    })


@company_admin_required
def order_detail(request, pk):
    """View details of a specific bulk order."""
    company = request.company
    order = get_object_or_404(BulkCardOrder, pk=pk, company=company)
    assignments = order.card_assignments.select_related('membership', 'card_product')
    pop_pending = order.proof_of_payments.filter(status='pending').exists()

    return render(request, 'companies/order_detail.html', {
        'company': company,
        'order': order,
        'assignments': assignments,
        'pop_pending': pop_pending,
    })


# ── Card Assignments ──

@company_admin_required
def card_assignments(request):
    """View and manage card assignments across the company."""
    company = request.company
    assignments = company.card_assignments.select_related(
        'membership', 'card_product', 'bulk_order'
    ).all()
    # Exclude employees who already have an assigned/active card
    already_assigned_ids = company.card_assignments.filter(
        status__in=('assigned', 'active'),
        membership__isnull=False,
    ).values_list('membership_id', flat=True)
    employees = company.memberships.filter(
        is_active=True, user__isnull=False
    ).exclude(pk__in=already_assigned_ids).select_related('user')

    return render(request, 'companies/card_assignments.html', {
        'company': company,
        'assignments': assignments,
        'employees': employees,
    })


@company_admin_required
def assign_card(request, pk):
    """Assign an unassigned card to an employee."""
    company = request.company
    assignment = get_object_or_404(CardAssignment, pk=pk, company=company, status='unassigned')

    if request.method == 'POST':
        member_pk = request.POST.get('member')
        membership = get_object_or_404(CompanyMembership, pk=member_pk, company=company, is_active=True)
        # Prevent double allocation
        if CardAssignment.objects.filter(
            company=company, membership=membership, status__in=('assigned', 'active')
        ).exists():
            messages.error(request, f'{membership.employee_name or membership.invite_email} already has a card assigned.')
            return redirect('companies:card_assignments')
        assignment.membership = membership
        assignment.status = 'assigned'
        assignment.assigned_at = timezone.now()
        assignment.save(update_fields=['membership', 'status', 'assigned_at'])
        messages.success(request, f'Card assigned to {membership.employee_name or membership.invite_email}.')
    return redirect('companies:card_assignments')


@company_admin_required
def unassign_card(request, pk):
    """Unassign a card from an employee."""
    company = request.company
    assignment = get_object_or_404(CardAssignment, pk=pk, company=company)

    if request.method == 'POST' and assignment.status in ('assigned', 'active'):
        assignment.membership = None
        assignment.status = 'unassigned'
        assignment.assigned_at = None
        assignment.save(update_fields=['membership', 'status', 'assigned_at'])
        messages.success(request, 'Card unassigned successfully.')
    return redirect('companies:card_assignments')


# ── Company Settings ──

@company_admin_required
def company_settings(request):
    """Edit company details and branding."""
    company = request.company

    if request.method == 'POST':
        form = CompanySettingsForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, 'Company settings updated.')
            return redirect('companies:settings')
    else:
        form = CompanySettingsForm(instance=company)

    return render(request, 'companies/settings.html', {
        'company': company,
        'form': form,
    })


@login_required
def user_profile(request):
    """Edit user profile (name, email, country)."""
    from django import forms
    from django_countries.fields import CountryField
    
    class UserProfileForm(forms.ModelForm):
        country = CountryField(blank_label='Select your country').formfield(
            required=True,
            widget=forms.Select(attrs={'class': 'country-select'}),
        )
        
        class Meta:
            model = User
            fields = ['first_name', 'last_name', 'email', 'country']
            widgets = {
                'first_name': forms.TextInput(attrs={'placeholder': 'First name'}),
                'last_name': forms.TextInput(attrs={'placeholder': 'Last name'}),
                'email': forms.EmailInput(attrs={'placeholder': 'you@example.com'}),
            }
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated.')
            return redirect('companies:user_profile')
    else:
        form = UserProfileForm(instance=request.user)
    
    return render(request, 'companies/user_profile.html', {
        'form': form,
    })


@login_required
def change_password(request):
    """Change user password."""
    from django.contrib.auth.forms import PasswordChangeForm
    from django.contrib.auth import update_session_auth_hash
    
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Keep user logged in
            messages.success(request, 'Your password has been changed successfully.')
            return redirect('companies:change_password')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'companies/change_password.html', {
        'form': form,
    })


# ── Company Subscription / Billing ──

def _period_days(period):
    return 365 if period == 'yearly' else 30

def _period_amount(plan, period):
    return plan.yearly_price if period == 'yearly' else plan.price

def _period_label(period):
    return 'year' if period == 'yearly' else 'month'


@company_admin_required
def company_billing(request):
    """Company billing dashboard — current plan, plans grid, billing history."""
    from subscriptions.models import Plan

    company = request.company
    subscription = None
    try:
        subscription = company.subscription
    except CompanySubscription.DoesNotExist:
        pass

    billing_events = company.billing_events.all()[:20]
    plans = Plan.objects.all()

    # Count NFC cards the company owns (from paid bulk orders)
    card_count = CardAssignment.objects.filter(company=company).count()
    card_count = max(card_count, 1)  # Minimum 1 card for billing

    # Compute total billed for current subscription
    total_billed = None
    if subscription:
        per_card = subscription.plan.yearly_price if subscription.billing_period == 'yearly' else subscription.plan.price
        total_billed = per_card * subscription.num_cards

    # Get enabled payment methods
    from subscriptions.models import PaymentMethodSettings
    enabled_payment_methods = PaymentMethodSettings.get_enabled_methods()
    
    # Filter payment methods based on user's country
    # Zimbabwe users (ZW) can use all methods, others only PayPal
    if request.user.country != 'ZW':
        enabled_payment_methods = [m for m in enabled_payment_methods if m == 'paypal']
    
    # Declined and pending cash orders for notification banners
    declined_cash_orders = BulkCardOrder.objects.filter(
        company=company, payment_method='cash', status='cancelled',
    ).exclude(rejection_reason='').order_by('-created_at')[:5]

    pending_cash_orders = BulkCardOrder.objects.filter(
        company=company, payment_method='cash', status='pending'
    ).order_by('-created_at')[:5]

    return render(request, 'companies/billing.html', {
        'company': company,
        'subscription': subscription,
        'billing_events': billing_events,
        'plans': plans,
        'card_count': card_count,
        'total_billed': total_billed,
        'bank_details': _get_bank_details(),
        'bank_accounts': _get_bank_accounts(),
        'enabled_payment_methods': enabled_payment_methods,
        'declined_cash_orders': declined_cash_orders,
        'pending_cash_orders': pending_cash_orders,
    })


@company_admin_required
def company_subscribe(request, plan_slug):
    """
    Subscribe to a plan. Accepts GET params: period, payment_method, ecocash_phone.
    Handles PayPal (dev skip), Bank Transfer (POP required), EcoCash (dev auto-approve).
    Pricing: plan_price × number_of_NFC_cards.
    """
    from datetime import timedelta
    from subscriptions.models import Plan

    company = request.company
    plan = get_object_or_404(Plan, slug=plan_slug)
    period = request.GET.get('period', 'monthly')
    payment_method = request.GET.get('payment_method', 'paypal')
    ecocash_phone = request.GET.get('ecocash_phone', '').strip()

    if period not in ('monthly', 'yearly'):
        period = 'monthly'
    if payment_method not in ('paypal', 'bank_transfer', 'ecocash', 'cash'):
        payment_method = 'paypal'

    days = _period_days(period)
    per_card_amount = _period_amount(plan, period)

    # Count NFC cards the company owns
    card_count = CardAssignment.objects.filter(company=company).count()
    card_count = max(card_count, 1)
    total_amount = per_card_amount * card_count

    # Check if already on this plan
    try:
        sub = company.subscription
        old_plan = sub.plan
        if old_plan.slug == plan_slug and sub.billing_period == period and sub.is_active():
            messages.info(request, f'{company.name} is already on the {plan.name} ({period}) plan.')
            return redirect('companies:billing')
    except CompanySubscription.DoesNotExist:
        sub = None
        old_plan = None

    # ── EcoCash: require phone number ──
    if payment_method == 'ecocash' and not ecocash_phone:
        messages.error(request, 'Please enter your EcoCash phone number.')
        return redirect('companies:billing')

    # ── Bank Transfer or Cash: create/update sub as pending, redirect to POP upload ──
    if payment_method in ('bank_transfer', 'cash'):
        method_label = 'Bank Transfer' if payment_method == 'bank_transfer' else 'Cash Payment'
        if sub:
            event_type = 'upgrade' if plan.price > old_plan.price else 'downgrade'
            sub.plan = plan
            sub.status = 'suspended'
            sub.billing_period = period
            sub.payment_method = payment_method
            sub.num_cards = card_count
            sub.save()
            CompanyBillingEvent.objects.create(
                company=company, event_type=event_type, plan=plan,
                amount=Decimal('0.00'),
                note=f'{event_type.title()} to {plan.name} ({period}) via {method_label} — awaiting approval ({card_count} cards × ${per_card_amount}, total ${total_amount})',
            )
        else:
            CompanySubscription.objects.create(
                company=company, plan=plan, status='suspended',
                billing_period=period, payment_method=payment_method,
                num_cards=card_count,
                expires_at=timezone.now(),
            )
            CompanyBillingEvent.objects.create(
                company=company, event_type='subscribe', plan=plan,
                amount=Decimal('0.00'),
                note=f'New {period} subscription to {plan.name} via {method_label} — awaiting approval ({card_count} cards × ${per_card_amount}, total ${total_amount})',
            )
        messages.success(
            request,
            f'Subscription to {plan.name} initiated! '
            f'Total: ${total_amount} ({card_count} card(s) × ${per_card_amount}/{_period_label(period)}). '
            f'Please transfer the amount to our bank account and upload your proof of payment.'
        )
        return redirect('companies:billing')

    # ── EcoCash ──
    if payment_method == 'ecocash':
        # PRODUCTION: Call EcoCash API here when available
        messages.info(request, f'EcoCash payment initiated to {ecocash_phone}. Check your phone for the prompt.')
        return redirect('companies:billing')

    # ── PayPal ──
    # Redirect to PayPal subscribe flow
    return redirect(
        reverse('companies:paypal_subscribe', args=[plan.slug]) + f'?period={period}'
    )


@company_admin_required
def company_paypal_subscribe(request, plan_slug):
    """Create a PayPal subscription for the company and redirect to PayPal for approval."""
    from subscriptions.models import Plan

    company = request.company
    plan = get_object_or_404(Plan, slug=plan_slug)
    period = request.GET.get('period', 'monthly')
    if period not in ('monthly', 'yearly'):
        period = 'monthly'

    pp_plan_id = plan.paypal_yearly_plan_id if period == 'yearly' else plan.paypal_plan_id
    if not pp_plan_id:
        messages.error(request, 'This plan is not yet available for PayPal checkout. Please contact support.')
        return redirect('companies:billing')

    # Check if already on this plan
    try:
        existing = company.subscription
        if existing.plan_id == plan.id and existing.billing_period == period and existing.is_active():
            messages.info(request, f'{company.name} is already on the {plan.name} ({period}) plan.')
            return redirect('companies:billing')
    except CompanySubscription.DoesNotExist:
        pass

    return_url = request.build_absolute_uri(
        reverse('companies:paypal_return') + f'?plan_slug={plan.slug}&period={period}'
    )
    cancel_url = request.build_absolute_uri(
        reverse('companies:paypal_cancel_return')
    )

    try:
        pp_sub_id, approval_url = paypal_api.create_subscription(
            paypal_plan_id=pp_plan_id,
            return_url=return_url,
            cancel_url=cancel_url,
            user_email=company.email or request.user.email,
        )
    except Exception as e:
        logger.error('Company PayPal create subscription failed: %s', e)
        messages.error(request, f'Unable to connect to PayPal: {e}')
        return redirect('companies:billing')

    if not approval_url:
        messages.error(request, 'PayPal did not return an approval URL. Please try again.')
        return redirect('companies:billing')

    request.session['pending_company_paypal_sub_id'] = pp_sub_id
    request.session['pending_company_plan_slug'] = plan.slug
    request.session['pending_company_period'] = period

    return redirect(approval_url)


@company_admin_required
def company_paypal_return(request):
    """PayPal redirects here after the company admin approves the subscription."""
    from datetime import timedelta
    from subscriptions.models import Plan

    company = request.company

    pp_sub_id = request.GET.get('subscription_id', '') or request.session.get('pending_company_paypal_sub_id', '')
    plan_slug = request.GET.get('plan_slug', '') or request.session.get('pending_company_plan_slug', '')
    period = request.GET.get('period', '') or request.session.get('pending_company_period', 'monthly')

    if period not in ('monthly', 'yearly'):
        period = 'monthly'

    logger.info('Company PayPal return: sub_id=%s, plan_slug=%s, period=%s', pp_sub_id, plan_slug, period)

    # Clean up session
    request.session.pop('pending_company_paypal_sub_id', None)
    request.session.pop('pending_company_plan_slug', None)
    request.session.pop('pending_company_period', None)

    if not pp_sub_id or not plan_slug:
        messages.error(request, 'Missing subscription details. Please try again.')
        return redirect('companies:billing')

    plan = get_object_or_404(Plan, slug=plan_slug)
    days = _period_days(period)
    amount = _period_amount(plan, period)

    # Verify with PayPal
    try:
        pp_details = paypal_api.get_subscription_details(pp_sub_id)
        logger.info('Company PayPal subscription %s status: %s', pp_sub_id, pp_details.get('status'))
    except Exception as e:
        logger.error('PayPal get subscription details failed for %s: %s', pp_sub_id, e)
        pp_details = {'status': 'APPROVED'}

    pp_status = pp_details.get('status', '')
    if pp_status not in ('ACTIVE', 'APPROVED', 'APPROVAL_PENDING'):
        messages.warning(
            request,
            f'Your PayPal subscription status is "{pp_status}". '
            'It may take a moment to activate. Please refresh or contact support.'
        )
        return redirect('companies:billing')

    # Activate or update local subscription
    try:
        sub = company.subscription
        old_plan = sub.plan
        event_type = 'upgrade' if plan.price > old_plan.price else ('downgrade' if plan.price < old_plan.price else 'renew')

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

        CompanyBillingEvent.objects.create(
            company=company,
            event_type=event_type,
            plan=plan,
            amount=amount,
            note=f'{event_type.title()} to {plan.name} ({period}) via PayPal ({pp_sub_id})',
        )
    except CompanySubscription.DoesNotExist:
        CompanySubscription.objects.create(
            company=company,
            plan=plan,
            status='active',
            billing_period=period,
            expires_at=timezone.now() + timedelta(days=days),
            paypal_subscription_id=pp_sub_id,
        )
        CompanyBillingEvent.objects.create(
            company=company,
            event_type='subscribe',
            plan=plan,
            amount=amount,
            note=f'New {period} subscription to {plan.name} via PayPal ({pp_sub_id})',
        )

    # Send subscription confirmation email
    try:
        company_sub = company.subscription
        send_company_subscription_confirmation(company_sub, amount=amount)
    except CompanySubscription.DoesNotExist:
        pass

    messages.success(request, f'Successfully subscribed {company.name} to {plan.name} ({period})!')
    return redirect('companies:billing')


@company_admin_required
def company_paypal_cancel_return(request):
    """User cancelled the PayPal approval flow."""
    request.session.pop('pending_company_paypal_sub_id', None)
    request.session.pop('pending_company_plan_slug', None)
    request.session.pop('pending_company_period', None)
    messages.info(request, 'PayPal checkout was cancelled. No changes were made.')
    return redirect('companies:billing')


@company_admin_required
def company_cancel_subscription(request):
    """Cancel the company subscription."""
    if request.method != 'POST':
        return redirect('companies:billing')

    company = request.company
    try:
        sub = company.subscription

        if sub.paypal_subscription_id:
            try:
                paypal_api.cancel_subscription(sub.paypal_subscription_id)
            except Exception as e:
                logger.error('Company PayPal cancel failed: %s', e)

        sub.status = 'cancelled'
        sub.paypal_subscription_id = ''
        sub.save()

        CompanyBillingEvent.objects.create(
            company=company,
            event_type='cancel',
            plan=sub.plan,
            amount=0,
            note=f'Cancelled {sub.plan.name} — access until {sub.expires_at.strftime("%b %d, %Y")}',
        )
        messages.success(request, f'Subscription cancelled. You still have access until {sub.expires_at.strftime("%b %d, %Y")}.')
    except CompanySubscription.DoesNotExist:
        messages.error(request, 'No active subscription to cancel.')

    return redirect('companies:billing')
