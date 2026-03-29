from django.core.management.base import BaseCommand
from subscriptions.models import PaymentMethodSettings


class Command(BaseCommand):
    help = 'Initialize default payment method settings'

    def handle(self, *args, **options):
        default_methods = [
            {
                'method': 'paypal',
                'display_name': 'PayPal',
                'description': 'PayPal recurring subscriptions and one-time payments',
                'is_enabled': True,
            },
            {
                'method': 'bank_transfer',
                'display_name': 'Bank Transfer',
                'description': 'Direct bank transfer with proof of payment upload',
                'is_enabled': True,
            },
            {
                'method': 'ecocash',
                'display_name': 'EcoCash',
                'description': 'Mobile money payment via EcoCash',
                'is_enabled': True,
            },
            {
                'method': 'cash',
                'display_name': 'Cash Payment',
                'description': 'Pay with cash on delivery or in-person, requires admin approval',
                'is_enabled': True,
            },
        ]

        created_count = 0
        for method_data in default_methods:
            obj, created = PaymentMethodSettings.objects.get_or_create(
                method=method_data['method'],
                defaults={
                    'display_name': method_data['display_name'],
                    'description': method_data['description'],
                    'is_enabled': method_data['is_enabled'],
                }
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created payment method: {obj.display_name}')
                )
            else:
                self.stdout.write(f'  Payment method already exists: {obj.display_name}')

        if created_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'\nSuccessfully initialized {created_count} payment method(s)')
            )
        else:
            self.stdout.write(self.style.WARNING('\nAll payment methods already initialized'))
