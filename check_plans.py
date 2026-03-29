import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'infinity_cards.settings')
django.setup()

from subscriptions.models import Plan

plans = Plan.objects.all()
print(f'Total plans in database: {plans.count()}\n')
print('=' * 70)

for p in plans:
    print(f'\n{p.name} (${p.price}/mo)')
    print(f'  Slug: {p.slug}')
    print(f'  PayPal Product ID: {p.paypal_product_id or "❌ MISSING"}')
    print(f'  PayPal Monthly Plan ID: {p.paypal_plan_id or "❌ MISSING"}')
    print(f'  PayPal Yearly Plan ID: {p.paypal_yearly_plan_id or "❌ MISSING"}')
    
    if not p.paypal_product_id or not p.paypal_plan_id or not p.paypal_yearly_plan_id:
        print(f'  ⚠️  WARNING: This plan is NOT fully synced with PayPal!')

print('\n' + '=' * 70)
missing = plans.filter(paypal_product_id='') | plans.filter(paypal_plan_id='')
if missing.exists():
    print(f'\n⚠️  {missing.count()} plan(s) need to be synced with PayPal')
    print('Run: python manage.py sync_paypal_plans')
else:
    print('\n✅ All plans are synced with PayPal!')
