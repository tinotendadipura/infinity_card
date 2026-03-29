from django import forms
from .models import CardOrder

COUNTRIES = [
    '', 'Afghanistan', 'Albania', 'Algeria', 'Andorra', 'Angola',
    'Antigua and Barbuda', 'Argentina', 'Armenia', 'Australia', 'Austria',
    'Azerbaijan', 'Bahamas', 'Bahrain', 'Bangladesh', 'Barbados', 'Belarus',
    'Belgium', 'Belize', 'Benin', 'Bhutan', 'Bolivia',
    'Bosnia and Herzegovina', 'Botswana', 'Brazil', 'Brunei', 'Bulgaria',
    'Burkina Faso', 'Burundi', 'Cabo Verde', 'Cambodia', 'Cameroon',
    'Canada', 'Central African Republic', 'Chad', 'Chile', 'China',
    'Colombia', 'Comoros', 'Congo (Brazzaville)', 'Congo (Kinshasa)',
    'Costa Rica', "Cote d'Ivoire", 'Croatia', 'Cuba', 'Cyprus',
    'Czech Republic', 'Denmark', 'Djibouti', 'Dominica',
    'Dominican Republic', 'Ecuador', 'Egypt', 'El Salvador',
    'Equatorial Guinea', 'Eritrea', 'Estonia', 'Eswatini', 'Ethiopia',
    'Fiji', 'Finland', 'France', 'Gabon', 'Gambia', 'Georgia', 'Germany',
    'Ghana', 'Greece', 'Grenada', 'Guatemala', 'Guinea', 'Guinea-Bissau',
    'Guyana', 'Haiti', 'Honduras', 'Hungary', 'Iceland', 'India',
    'Indonesia', 'Iran', 'Iraq', 'Ireland', 'Israel', 'Italy', 'Jamaica',
    'Japan', 'Jordan', 'Kazakhstan', 'Kenya', 'Kiribati', 'Kosovo',
    'Kuwait', 'Kyrgyzstan', 'Laos', 'Latvia', 'Lebanon', 'Lesotho',
    'Liberia', 'Libya', 'Liechtenstein', 'Lithuania', 'Luxembourg',
    'Madagascar', 'Malawi', 'Malaysia', 'Maldives', 'Mali', 'Malta',
    'Marshall Islands', 'Mauritania', 'Mauritius', 'Mexico', 'Micronesia',
    'Moldova', 'Monaco', 'Mongolia', 'Montenegro', 'Morocco', 'Mozambique',
    'Myanmar', 'Namibia', 'Nauru', 'Nepal', 'Netherlands', 'New Zealand',
    'Nicaragua', 'Niger', 'Nigeria', 'North Korea', 'North Macedonia',
    'Norway', 'Oman', 'Pakistan', 'Palau', 'Palestine', 'Panama',
    'Papua New Guinea', 'Paraguay', 'Peru', 'Philippines', 'Poland',
    'Portugal', 'Qatar', 'Romania', 'Russia', 'Rwanda',
    'Saint Kitts and Nevis', 'Saint Lucia',
    'Saint Vincent and the Grenadines', 'Samoa', 'San Marino',
    'Sao Tome and Principe', 'Saudi Arabia', 'Senegal', 'Serbia',
    'Seychelles', 'Sierra Leone', 'Singapore', 'Slovakia', 'Slovenia',
    'Solomon Islands', 'Somalia', 'South Africa', 'South Korea',
    'South Sudan', 'Spain', 'Sri Lanka', 'Sudan', 'Suriname', 'Sweden',
    'Switzerland', 'Syria', 'Taiwan', 'Tajikistan', 'Tanzania', 'Thailand',
    'Timor-Leste', 'Togo', 'Tonga', 'Trinidad and Tobago', 'Tunisia',
    'Turkey', 'Turkmenistan', 'Tuvalu', 'Uganda', 'Ukraine',
    'United Arab Emirates', 'United Kingdom', 'United States', 'Uruguay',
    'Uzbekistan', 'Vanuatu', 'Vatican City', 'Venezuela', 'Vietnam',
    'Yemen', 'Zambia', 'Zimbabwe',
]

COUNTRY_CHOICES = [(c, c) if c else ('', 'Select a country') for c in COUNTRIES]


class CheckoutAddressForm(forms.ModelForm):
    """Shopify-style shipping address form for card checkout."""

    class Meta:
        model = CardOrder
        fields = [
            'shipping_first_name',
            'shipping_last_name',
            'shipping_email',
            'shipping_phone',
            'shipping_address1',
            'shipping_address2',
            'shipping_city',
            'shipping_state',
            'shipping_zip',
            'shipping_country',
        ]
        widgets = {
            'shipping_first_name': forms.TextInput(attrs={
                'placeholder': 'First name', 'autocomplete': 'given-name',
            }),
            'shipping_last_name': forms.TextInput(attrs={
                'placeholder': 'Last name', 'autocomplete': 'family-name',
            }),
            'shipping_email': forms.EmailInput(attrs={
                'placeholder': 'Email address', 'autocomplete': 'email',
            }),
            'shipping_phone': forms.TextInput(attrs={
                'placeholder': 'Phone number', 'autocomplete': 'tel',
            }),
            'shipping_address1': forms.TextInput(attrs={
                'placeholder': 'Address', 'autocomplete': 'address-line1',
            }),
            'shipping_address2': forms.TextInput(attrs={
                'placeholder': 'Apartment, suite, etc. (optional)', 'autocomplete': 'address-line2',
            }),
            'shipping_city': forms.TextInput(attrs={
                'placeholder': 'City', 'autocomplete': 'address-level2',
            }),
            'shipping_state': forms.TextInput(attrs={
                'placeholder': 'State / Province', 'autocomplete': 'address-level1',
            }),
            'shipping_zip': forms.TextInput(attrs={
                'placeholder': 'ZIP / Postal code', 'autocomplete': 'postal-code',
            }),
            'shipping_country': forms.Select(
                choices=COUNTRY_CHOICES,
                attrs={'autocomplete': 'country-name', 'id': 'id_shipping_country'},
            ),
        }
        labels = {
            'shipping_first_name': 'First name',
            'shipping_last_name': 'Last name',
            'shipping_email': 'Email',
            'shipping_phone': 'Phone',
            'shipping_address1': 'Address',
            'shipping_address2': 'Apartment, suite, etc.',
            'shipping_city': 'City',
            'shipping_state': 'State / Province',
            'shipping_zip': 'ZIP / Postal code',
            'shipping_country': 'Country / Region',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        for field_name in ['shipping_first_name', 'shipping_last_name', 'shipping_email',
                           'shipping_phone', 'shipping_address1', 'shipping_city',
                           'shipping_state', 'shipping_zip', 'shipping_country']:
            self.fields[field_name].required = True
        if user:
            if not self.initial.get('shipping_first_name'):
                self.initial['shipping_first_name'] = user.first_name
            if not self.initial.get('shipping_last_name'):
                self.initial['shipping_last_name'] = user.last_name
            if not self.initial.get('shipping_email'):
                self.initial['shipping_email'] = user.email
