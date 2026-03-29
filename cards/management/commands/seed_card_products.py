from django.core.management.base import BaseCommand
from cards.models import NFCCardProduct


CARD_PRODUCTS = [
    {
        'name': 'Plastic NFC Card',
        'slug': 'plastic',
        'material': 'plastic',
        'price': '10.00',
        'custom_price': '35.00',
        'description': 'Classic matte-finish plastic NFC business card. Lightweight, durable, and professional.',
        'sort_order': 1,
    },
    {
        'name': 'Plastic Gold NFC Card',
        'slug': 'plastic-gold',
        'material': 'plastic_gold',
        'price': '15.00',
        'custom_price': '40.00',
        'description': 'Premium plastic card with a luxurious gold finish. Stand out with elegance.',
        'sort_order': 2,
    },
    {
        'name': 'Plastic Transparent NFC Card',
        'slug': 'plastic-transparent',
        'material': 'plastic_transparent',
        'price': '10.00',
        'custom_price': '35.00',
        'description': 'Sleek see-through plastic NFC card. Modern and eye-catching.',
        'sort_order': 3,
    },
    {
        'name': 'Wood NFC Card',
        'slug': 'wood',
        'material': 'wood',
        'price': '25.00',
        'custom_price': '50.00',
        'description': 'Eco-friendly wooden NFC business card. Natural texture with a premium feel.',
        'sort_order': 4,
    },
    {
        'name': 'Metal NFC Card',
        'slug': 'metal',
        'material': 'metal',
        'price': '50.00',
        'custom_price': '75.00',
        'description': 'Heavy-duty stainless steel NFC card. The ultimate premium business card.',
        'sort_order': 5,
    },
]


class Command(BaseCommand):
    help = 'Seed the database with the 5 NFC card product types'

    def handle(self, *args, **options):
        for data in CARD_PRODUCTS:
            product, created = NFCCardProduct.objects.update_or_create(
                material=data['material'],
                defaults=data,
            )
            status = 'Created' if created else 'Updated'
            self.stdout.write(f'  {status}: {product.name} (${product.price})')

        self.stdout.write(self.style.SUCCESS('Done! All card products seeded.'))
