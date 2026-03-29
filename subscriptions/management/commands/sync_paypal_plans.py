"""
Management command to sync local Plan models with PayPal.

For each Plan that is missing a paypal_product_id or paypal_plan_id,
this command creates the corresponding PayPal Product and Billing Plan,
then stores the IDs back on the local Plan model.

Usage:
    python manage.py sync_paypal_plans
    python manage.py sync_paypal_plans --force   # re-create even if IDs exist
"""
from django.core.management.base import BaseCommand

from subscriptions.models import Plan
from subscriptions import paypal as paypal_api


class Command(BaseCommand):
    help = 'Create PayPal Products and Billing Plans for each local Plan'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-create PayPal products/plans even if IDs already exist',
        )

    def handle(self, *args, **options):
        force = options['force']
        plans = Plan.objects.all()

        if not plans.exists():
            self.stderr.write(self.style.WARNING('No plans found. Run seed_plans first.'))
            return

        for plan in plans:
            self.stdout.write(f'\n-- {plan.name} (${plan.price}/mo) --')

            # Skip free plans (price == 0)
            if plan.price <= 0:
                self.stdout.write(self.style.WARNING('  Skipped (free plan, no PayPal billing needed)'))
                continue

            # Create PayPal Product
            if not plan.paypal_product_id or force:
                try:
                    product_id = paypal_api.create_product(
                        name=f'InfinityCard {plan.name}',
                        description=plan.description or f'{plan.name} subscription plan',
                    )
                    plan.paypal_product_id = product_id
                    self.stdout.write(self.style.SUCCESS(f'  Product created: {product_id}'))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'  Failed to create product: {e}'))
                    continue
            else:
                self.stdout.write(f'  Product exists: {plan.paypal_product_id}')

            # Create PayPal Monthly Billing Plan
            if not plan.paypal_plan_id or force:
                try:
                    billing_plan_id = paypal_api.create_billing_plan(
                        product_id=plan.paypal_product_id,
                        plan_name=plan.name,
                        price=plan.price,
                    )
                    plan.paypal_plan_id = billing_plan_id
                    self.stdout.write(self.style.SUCCESS(f'  Monthly plan created: {billing_plan_id}'))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'  Failed to create monthly plan: {e}'))
                    continue
            else:
                self.stdout.write(f'  Monthly plan exists: {plan.paypal_plan_id}')

            # Create PayPal Yearly Billing Plan (with discount)
            if not plan.paypal_yearly_plan_id or force:
                try:
                    yearly_plan_id = paypal_api.create_billing_plan(
                        product_id=plan.paypal_product_id,
                        plan_name=f'{plan.name} Yearly',
                        price=plan.yearly_price,
                        interval_unit='YEAR',
                        interval_count=1,
                    )
                    plan.paypal_yearly_plan_id = yearly_plan_id
                    self.stdout.write(self.style.SUCCESS(
                        f'  Yearly plan created: {yearly_plan_id} '
                        f'(${plan.yearly_price}/yr, {plan.yearly_discount_percent}% off)'
                    ))
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'  Failed to create yearly plan: {e}'))
            else:
                self.stdout.write(f'  Yearly plan exists: {plan.paypal_yearly_plan_id}')

            plan.save(update_fields=['paypal_product_id', 'paypal_plan_id', 'paypal_yearly_plan_id'])

        self.stdout.write(self.style.SUCCESS('\nDone! All plans synced with PayPal.'))
