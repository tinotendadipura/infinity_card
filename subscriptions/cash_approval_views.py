"""View functions for approving cash payment orders (personal and company)."""
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone


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
    
    messages.success(request, f'Cash payment approved — bulk order #{order.pk} activated.')
    return redirect('subscriptions:admin_approvals')
