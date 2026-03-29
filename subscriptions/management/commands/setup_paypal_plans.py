"""
Management command to create PayPal products and billing plans for all subscription plans.
Usage: python manage.py setup_paypal_plans
"""
from django.core.management.base import BaseCommand
from subscriptions.models import Plan
from subscriptions import paypal as paypal_api


class Command(BaseCommand):
    help = 'Create PayPal products and billing plans for all subscription plans'

    def handle(self, *args, **options):
        plans = Plan.objects.all()
        
        if not plans.exists():
            self.stdout.write(self.style.ERROR('No plans found in database. Please create plans first.'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'Found {plans.count()} plan(s). Setting up PayPal integration...'))
        
        for plan in plans:
            self.stdout.write(f'\n--- Processing: {plan.name} ---')
            
            # Step 1: Create PayPal Product (if not exists)
            if not plan.paypal_product_id:
                try:
                    product_id = paypal_api.create_product(
                        name=plan.name,
                        description=plan.description or f'{plan.name} subscription plan'
                    )
                    plan.paypal_product_id = product_id
                    plan.save(update_fields=['paypal_product_id'])
                    self.stdout.write(self.style.SUCCESS(f'[OK] Created PayPal product: {product_id}'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'[ERROR] Failed to create product: {e}'))
                    continue
            else:
                self.stdout.write(f'[OK] Product already exists: {plan.paypal_product_id}')
            
            # Step 2: Create Monthly Billing Plan (if not exists)
            if not plan.paypal_plan_id:
                try:
                    monthly_plan_id = paypal_api.create_billing_plan(
                        product_id=plan.paypal_product_id,
                        plan_name=plan.name,
                        price=plan.price,
                        interval_unit='MONTH',
                        interval_count=1
                    )
                    plan.paypal_plan_id = monthly_plan_id
                    plan.save(update_fields=['paypal_plan_id'])
                    self.stdout.write(self.style.SUCCESS(f'[OK] Created monthly plan: {monthly_plan_id} (${plan.price}/month)'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'[ERROR] Failed to create monthly plan: {e}'))
            else:
                self.stdout.write(f'[OK] Monthly plan already exists: {plan.paypal_plan_id}')
            
            # Step 3: Create Yearly Billing Plan (if not exists)
            if not plan.paypal_yearly_plan_id:
                try:
                    yearly_price = plan.yearly_price
                    yearly_plan_id = paypal_api.create_billing_plan(
                        product_id=plan.paypal_product_id,
                        plan_name=plan.name,
                        price=yearly_price,
                        interval_unit='YEAR',
                        interval_count=1
                    )
                    plan.paypal_yearly_plan_id = yearly_plan_id
                    plan.save(update_fields=['paypal_yearly_plan_id'])
                    self.stdout.write(self.style.SUCCESS(f'[OK] Created yearly plan: {yearly_plan_id} (${yearly_price}/year)'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'[ERROR] Failed to create yearly plan: {e}'))
            else:
                self.stdout.write(f'[OK] Yearly plan already exists: {plan.paypal_yearly_plan_id}')
        
        self.stdout.write(self.style.SUCCESS('\n[SUCCESS] PayPal setup complete!'))
        self.stdout.write('\nPlan Summary:')
        for plan in Plan.objects.all():
            self.stdout.write(f'\n{plan.name}:')
            self.stdout.write(f'  Product ID: {plan.paypal_product_id or "NOT SET"}')
            self.stdout.write(f'  Monthly Plan: {plan.paypal_plan_id or "NOT SET"}')
            self.stdout.write(f'  Yearly Plan: {plan.paypal_yearly_plan_id or "NOT SET"}')
