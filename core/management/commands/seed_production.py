"""
Production seed script for InfinityCard platform.

Creates all required initial data for a fresh database:
  1. Subscription plans (Starter, Business, Pro)
  2. Profile categories (24 industry categories with icons)
  3. NFC card products (5 material types)
  4. Themes (5 color themes)
  5. Payment method settings (PayPal, Bank Transfer, EcoCash, Cash)
  6. Banking details (primary bank account)
  7. Superuser account (optional, prompted)

Usage:
    python manage.py seed_production
    python manage.py seed_production --no-superuser
    python manage.py seed_production --verbosity 2
"""

import getpass
import sys

from django.core.management.base import BaseCommand
from django.db import transaction


# ═══════════════════════════════════════════════════════════════
#  1. SUBSCRIPTION PLANS
# ═══════════════════════════════════════════════════════════════
PLANS = [
    {
        'name': 'Starter',
        'slug': 'starter',
        'price': '3.00',
        'features': {'max_images': 5, 'analytics': False},
        'description': 'Perfect for getting started. Basic profile with essential features.',
        'badge_label': '',
        'is_highlighted': False,
        'yearly_discount_percent': 20,
    },
    {
        'name': 'Business',
        'slug': 'business',
        'price': '5.00',
        'features': {'max_images': 20, 'analytics': True},
        'description': 'Ideal for professionals. Tap analytics and more images.',
        'badge_label': 'Popular',
        'is_highlighted': True,
        'yearly_discount_percent': 20,
    },
    {
        'name': 'Pro',
        'slug': 'pro',
        'price': '10.00',
        'features': {'max_images': 50, 'analytics': True, 'custom_theme': True},
        'description': 'Everything you need. Custom themes, full analytics, max uploads.',
        'badge_label': 'Best Value',
        'is_highlighted': False,
        'yearly_discount_percent': 20,
    },
]


# ═══════════════════════════════════════════════════════════════
#  2. CATEGORIES
# ═══════════════════════════════════════════════════════════════
CATEGORIES = [
    {
        'name': 'Agriculture',
        'slug': 'agriculture',
        'description': 'Profile for farms, agribusinesses, and agricultural services.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/>',
        'icon_color': '#A3E635',
        'icon_bg': 'rgba(101,163,13,.15)',
    },
    {
        'name': 'Automotive',
        'slug': 'automotive',
        'description': 'Profile for mechanics, car dealerships, and auto service providers.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M21.75 6.75a4.5 4.5 0 01-4.884 4.484c-1.076-.091-2.264.071-2.95.904l-7.152 8.684a2.548 2.548 0 11-3.586-3.586l8.684-7.152c.833-.686.995-1.874.904-2.95a4.5 4.5 0 016.336-4.486l-3.276 3.276a3.004 3.004 0 002.25 2.25l3.276-3.276c.256.565.398 1.192.398 1.852z"/>',
        'icon_color': '#A1A1AA',
        'icon_bg': 'rgba(113,113,122,.15)',
    },
    {
        'name': 'Beauty & Salon',
        'slug': 'beauty',
        'description': 'Profile for salons, spas, barbers, and beauty professionals.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z"/>',
        'icon_color': '#F9A8D4',
        'icon_bg': 'rgba(236,72,153,.15)',
    },
    {
        'name': 'Business',
        'slug': 'business',
        'description': 'A professional profile for companies, agencies, and organizations.',
        'fields_config': {
            'sections': ['bio', 'services', 'contact', 'social_links', 'cta'],
            'cta_label': 'Get in Touch',
        },
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M20.25 14.15v4.25c0 1.094-.787 2.036-1.872 2.18-2.087.277-4.216.42-6.378.42s-4.291-.143-6.378-.42c-1.085-.144-1.872-1.086-1.872-2.18v-4.25m16.5 0a2.18 2.18 0 00.75-1.661V8.706c0-1.081-.768-2.015-1.837-2.175a48.114 48.114 0 00-3.413-.387m4.5 8.006c-.194.165-.42.295-.673.38A23.978 23.978 0 0112 15.75c-2.648 0-5.195-.429-7.577-1.22a2.016 2.016 0 01-.673-.38m0 0A2.18 2.18 0 013 12.489V8.706c0-1.081.768-2.015 1.837-2.175a48.111 48.111 0 013.413-.387m7.5 0V5.25A2.25 2.25 0 0013.5 3h-3a2.25 2.25 0 00-2.25 2.25v.894m7.5 0a48.667 48.667 0 00-7.5 0M12 12.75h.008v.008H12v-.008z"/>',
        'icon_color': '#FB923C',
        'icon_bg': 'rgba(234,88,12,.15)',
    },
    {
        'name': 'Construction',
        'slug': 'construction',
        'description': 'Profile for contractors, builders, and construction firms.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l5.653-4.655m2.588 2.588a2.082 2.082 0 01-2.845-.095l-.108-.107a2.082 2.082 0 01-.095-2.845m7.48-5.528l-3.96 3.96m0 0l-2.588-2.588m2.588 2.588l4.655-5.653a2.548 2.548 0 013.586 3.586l-5.653 4.655"/>',
        'icon_color': '#FDBA74',
        'icon_bg': 'rgba(249,115,22,.15)',
    },
    {
        'name': 'Consulting',
        'slug': 'consulting',
        'description': 'Profile for consultants, advisors, and strategy professionals.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155"/>',
        'icon_color': '#60A5FA',
        'icon_bg': 'rgba(37,99,235,.15)',
    },
    {
        'name': 'Creative',
        'slug': 'creative',
        'description': 'Portfolio profile for designers, artists, photographers, and creatives.',
        'fields_config': {
            'sections': ['bio', 'gallery', 'services', 'contact', 'social_links', 'cta'],
            'cta_label': 'Book a Session',
        },
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"/><path stroke-linecap="round" stroke-linejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z"/>',
        'icon_color': '#C4B5FD',
        'icon_bg': 'rgba(168,85,247,.15)',
    },
    {
        'name': 'Education',
        'slug': 'education',
        'description': 'Profile for tutors, schools, coaches, and educational institutions.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M4.26 10.147a60.436 60.436 0 00-.491 6.347A48.627 48.627 0 0112 20.904a48.627 48.627 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.57 50.57 0 00-2.658-.813A59.905 59.905 0 0112 3.493a59.902 59.902 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.697 50.697 0 0112 13.489a50.702 50.702 0 017.74-3.342M6.75 15a.75.75 0 100-1.5.75.75 0 000 1.5zm0 0v-3.675A55.378 55.378 0 0112 8.443m-7.007 11.55A5.981 5.981 0 006.75 15.75v-1.5"/>',
        'icon_color': '#93C5FD',
        'icon_bg': 'rgba(59,130,246,.15)',
    },
    {
        'name': 'Events',
        'slug': 'events',
        'description': 'Event planning and management profile with packages and booking info.',
        'fields_config': {
            'sections': ['bio', 'packages', 'gallery', 'contact', 'social_links', 'cta'],
            'cta_label': 'Get a Quote',
        },
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5m-9-6h.008v.008H12v-.008zM12 15h.008v.008H12V15zm0 2.25h.008v.008H12v-.008zM9.75 15h.008v.008H9.75V15zm0 2.25h.008v.008H9.75v-.008zM7.5 15h.008v.008H7.5V15zm0 2.25h.008v.008H7.5v-.008zm6.75-4.5h.008v.008h-.008v-.008zm0 2.25h.008v.008h-.008V15zm0 2.25h.008v.008h-.008v-.008zm2.25-4.5h.008v.008H16.5v-.008zm0 2.25h.008v.008H16.5V15z"/>',
        'icon_color': '#FDA4AF',
        'icon_bg': 'rgba(225,29,72,.15)',
    },
    {
        'name': 'Fashion',
        'slug': 'fashion',
        'description': 'Profile for fashion designers, boutiques, and clothing brands.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007zM8.625 10.5a.375.375 0 11-.75 0 .375.375 0 01.75 0zm7.5 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"/>',
        'icon_color': '#E879F9',
        'icon_bg': 'rgba(192,38,211,.15)',
    },
    {
        'name': 'Finance',
        'slug': 'finance',
        'description': 'Profile for accountants, financial advisors, and banking professionals.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z"/>',
        'icon_color': '#86EFAC',
        'icon_bg': 'rgba(34,197,94,.15)',
    },
    {
        'name': 'Fitness',
        'slug': 'fitness',
        'description': 'Profile for personal trainers, gyms, and fitness professionals.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"/>',
        'icon_color': '#FCD34D',
        'icon_bg': 'rgba(245,158,11,.15)',
    },
    {
        'name': 'Freelancer',
        'slug': 'freelancer',
        'description': 'Showcase your freelance skills, portfolio, and availability.',
        'fields_config': {
            'sections': ['bio', 'skills', 'portfolio', 'contact', 'social_links', 'cta'],
            'cta_label': 'Hire Me',
        },
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25A2.25 2.25 0 015.25 3h13.5A2.25 2.25 0 0121 5.25z"/>',
        'icon_color': '#7DD3FC',
        'icon_bg': 'rgba(2,132,199,.15)',
    },
    {
        'name': 'Healthcare',
        'slug': 'healthcare',
        'description': 'Profile for doctors, clinics, therapists, and medical professionals.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z"/>',
        'icon_color': '#F87171',
        'icon_bg': 'rgba(239,68,68,.15)',
    },
    {
        'name': 'Legal',
        'slug': 'legal',
        'description': 'Profile for attorneys, law firms, and legal consultants.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M12 3v17.25m0 0c-1.472 0-2.882.265-4.185.75M12 20.25c1.472 0 2.882.265 4.185.75M18.75 4.97A48.416 48.416 0 0012 4.5c-2.291 0-4.545.16-6.75.47m13.5 0c1.01.143 2.01.317 3 .52m-3-.52l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.988 5.988 0 01-2.031.352 5.988 5.988 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L18.75 4.971zm-16.5.52c.99-.203 1.99-.377 3-.52m0 0l2.62 10.726c.122.499-.106 1.028-.589 1.202a5.989 5.989 0 01-2.031.352 5.989 5.989 0 01-2.031-.352c-.483-.174-.711-.703-.59-1.202L5.25 4.971z"/>',
        'icon_color': '#94A3B8',
        'icon_bg': 'rgba(100,116,139,.15)',
    },
    {
        'name': 'Music & Entertainment',
        'slug': 'music',
        'description': 'Profile for musicians, DJs, bands, and entertainers.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 15.553z"/>',
        'icon_color': '#A78BFA',
        'icon_bg': 'rgba(139,92,246,.15)',
    },
    {
        'name': 'Non-Profit',
        'slug': 'nonprofit',
        'description': 'Profile for charities, NGOs, and community organizations.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M10.05 4.575a1.575 1.575 0 10-3.15 0v3m3.15-3v-1.5a1.575 1.575 0 013.15 0v1.5m-3.15 0l.075 5.925m3.075-5.925a1.575 1.575 0 013.15 0v1.5m-3.15-1.5v6m3.15-4.5v6m0 0v1.5a1.575 1.575 0 01-1.575 1.575H9.86a4.725 4.725 0 01-3.342-1.384l-3.042-3.043a1.575 1.575 0 012.228-2.228l.879.879V4.575"/>',
        'icon_color': '#5EEAD4',
        'icon_bg': 'rgba(20,184,166,.15)',
    },
    {
        'name': 'Personal',
        'slug': 'personal',
        'description': 'A personal digital business card for networking and professional connections.',
        'fields_config': {
            'sections': ['bio', 'contact', 'social_links'],
            'cta_label': 'Connect',
        },
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"/>',
        'icon_color': '#A5B4FC',
        'icon_bg': 'rgba(99,102,241,.15)',
    },
    {
        'name': 'Photography',
        'slug': 'photography',
        'description': 'Profile for photographers with portfolio showcasing.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"/>',
        'icon_color': '#FDE68A',
        'icon_bg': 'rgba(217,119,6,.15)',
    },
    {
        'name': 'Real Estate',
        'slug': 'real_estate',
        'description': 'Display property listings, locations, and agent contact information.',
        'fields_config': {
            'sections': ['bio', 'listings', 'contact', 'social_links', 'cta'],
            'cta_label': 'View Listings',
        },
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M8.25 21v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21m0 0h4.5V3.545M12.75 21h7.5V10.75M2.25 21h1.5m18 0h-18M2.25 9l4.5-1.636M18.75 3l-1.5.545m0 6.205l3 1m1.5.5l-1.5-.5M6.75 7.364V3h-3v18m3-13.636l10.5-3.819"/>',
        'icon_color': '#34D399',
        'icon_bg': 'rgba(5,150,105,.15)',
    },
    {
        'name': 'Restaurant',
        'slug': 'restaurant',
        'description': 'Showcase your restaurant menu, ambiance, and contact details.',
        'fields_config': {
            'sections': ['bio', 'menu', 'hours', 'location', 'contact', 'cta'],
            'cta_label': 'Order Now',
        },
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M12 8.25v-1.5m0 1.5c-1.355 0-2.697.056-4.024.166C6.845 8.51 6 9.473 6 10.608v2.513m6-4.871c1.355 0 2.697.056 4.024.166C17.155 8.51 18 9.473 18 10.608v2.513M15 8.25v-1.5m-6 1.5v-1.5m12 9.75l-1.5.75a3.354 3.354 0 01-3 0 3.354 3.354 0 00-3 0 3.354 3.354 0 01-3 0 3.354 3.354 0 00-3 0 3.354 3.354 0 01-3 0L3 16.5m15-3.379a48.474 48.474 0 00-6-.371c-2.032 0-4.034.126-6 .371m12 0c.39.049.777.102 1.163.16 1.07.16 1.837 1.094 1.837 2.175v5.169c0 .621-.504 1.125-1.125 1.125H4.125A1.125 1.125 0 013 20.625v-5.17c0-1.08.768-2.014 1.837-2.174A47.78 47.78 0 016 13.12M12.265 3.11a.375.375 0 11-.53 0L12 2.845l.265.265z"/>',
        'icon_color': '#FCA5A5',
        'icon_bg': 'rgba(220,38,38,.15)',
    },
    {
        'name': 'Retail & Shop',
        'slug': 'retail',
        'description': 'Profile for retail stores, e-commerce shops, and product sellers.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M13.5 21v-7.5a.75.75 0 01.75-.75h3a.75.75 0 01.75.75V21m-4.5 0H2.36a1.11 1.11 0 01-1.085-.918l-1.08-6.48A1.125 1.125 0 011.32 12.5h2.43m17.5 8.5H2.36m19.14 0a1.11 1.11 0 001.085-.918l1.08-6.48A1.125 1.125 0 0022.68 12.5h-2.43m-17.5 0h17.5m-17.5 0l1.395-4.186A1.125 1.125 0 015.77 7.25h12.46a1.125 1.125 0 011.07 1.064L20.75 12.5"/>',
        'icon_color': '#BEF264',
        'icon_bg': 'rgba(132,204,22,.15)',
    },
    {
        'name': 'Technology',
        'slug': 'technology',
        'description': 'Profile for tech companies, developers, and IT service providers.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25zm.75-12h9v9h-9v-9z"/>',
        'icon_color': '#67E8F9',
        'icon_bg': 'rgba(6,182,212,.15)',
    },
    {
        'name': 'Travel & Tourism',
        'slug': 'travel',
        'description': 'Profile for travel agencies, tour guides, and hospitality businesses.',
        'fields_config': {},
        'icon': '<path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418"/>',
        'icon_color': '#6EE7B7',
        'icon_bg': 'rgba(16,185,129,.15)',
    },
]


# ═══════════════════════════════════════════════════════════════
#  3. NFC CARD PRODUCTS
# ═══════════════════════════════════════════════════════════════
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


# ═══════════════════════════════════════════════════════════════
#  4. THEMES
# ═══════════════════════════════════════════════════════════════
THEMES = [
    {
        'name': 'InfinityCard Classic',
        'primary_color': '#2EC4B6',
        'secondary_color': '#6B2FA0',
        'background_color': '#FFFFFF',
        'text_color': '#1E293B',
        'is_default': True,
    },
    {
        'name': 'Deep Purple',
        'primary_color': '#6B2FA0',
        'secondary_color': '#2EC4B6',
        'background_color': '#F5F3FF',
        'text_color': '#1E1B4B',
        'is_default': False,
    },
    {
        'name': 'Midnight',
        'primary_color': '#8B5CF6',
        'secondary_color': '#2EC4B6',
        'background_color': '#0F172A',
        'text_color': '#E2E8F0',
        'is_default': False,
    },
    {
        'name': 'Forest',
        'primary_color': '#10B981',
        'secondary_color': '#6B2FA0',
        'background_color': '#F0FDF4',
        'text_color': '#14532D',
        'is_default': False,
    },
    {
        'name': 'Coral Sunset',
        'primary_color': '#F97316',
        'secondary_color': '#6B2FA0',
        'background_color': '#FFF7ED',
        'text_color': '#431407',
        'is_default': False,
    },
]


# ═══════════════════════════════════════════════════════════════
#  5. PAYMENT METHODS
# ═══════════════════════════════════════════════════════════════
PAYMENT_METHODS = [
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


# ═══════════════════════════════════════════════════════════════
#  6. BANKING DETAILS
# ═══════════════════════════════════════════════════════════════
BANKING_DETAILS = [
    {
        'bank_name': 'FBC Bank',
        'account_name': 'InfinityCard Technologies',
        'account_number': '6280 1234 5678 90',
        'branch': 'Harare Main Branch',
        'branch_code': '6280',
        'swift_code': 'FBCPZWHA',
        'currency': 'USD',
        'is_active': True,
        'is_primary': True,
    },
]


class Command(BaseCommand):
    help = (
        'Seed the production database with all required initial data: '
        'plans, categories, card products, themes, payment methods, '
        'banking details, and optionally a superuser account.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-superuser',
            action='store_true',
            help='Skip superuser creation prompt',
        )
        parser.add_argument(
            '--no-input',
            action='store_true',
            help='Run non-interactively (skip all prompts, no superuser)',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('=' * 60))
        self.stdout.write(self.style.HTTP_INFO('  InfinityCard - Production Database Seeder'))
        self.stdout.write(self.style.HTTP_INFO('=' * 60))
        self.stdout.write('')

        self._seed_plans()
        self._seed_categories()
        self._seed_card_products()
        self._seed_themes()
        self._seed_payment_methods()
        self._seed_banking_details()

        if not options.get('no_superuser') and not options.get('no_input'):
            self._create_superuser()

        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('=' * 60))
        self.stdout.write(self.style.SUCCESS('  All done! Platform is ready.'))
        self.stdout.write(self.style.HTTP_INFO('=' * 60))
        self.stdout.write('')

    # ───────────────────────────────────────────────────────
    def _seed_plans(self):
        from subscriptions.models import Plan

        self.stdout.write(self.style.MIGRATE_HEADING('\n[1/6] Subscription Plans'))
        created = 0
        for data in PLANS:
            _, is_new = Plan.objects.update_or_create(
                slug=data['slug'], defaults=data,
            )
            label = 'Created' if is_new else 'Exists '
            style = self.style.SUCCESS if is_new else self.style.WARNING
            self.stdout.write(f'  {style(label)}  {data["name"]} (${data["price"]}/mo)')
            if is_new:
                created += 1
        self.stdout.write(f'  -> {created} new, {len(PLANS) - created} existing')

    # ───────────────────────────────────────────────────────
    def _seed_categories(self):
        from categories.models import Category

        self.stdout.write(self.style.MIGRATE_HEADING('\n[2/6] Profile Categories'))
        created = 0
        for data in CATEGORIES:
            _, is_new = Category.objects.update_or_create(
                slug=data['slug'], defaults=data,
            )
            if is_new:
                created += 1
        self.stdout.write(f'  -> {created} new, {len(CATEGORIES) - created} existing')
        self.stdout.write(f'  -> {len(CATEGORIES)} total categories')

    # ───────────────────────────────────────────────────────
    def _seed_card_products(self):
        from cards.models import NFCCardProduct

        self.stdout.write(self.style.MIGRATE_HEADING('\n[3/6] NFC Card Products'))
        created = 0
        for data in CARD_PRODUCTS:
            _, is_new = NFCCardProduct.objects.update_or_create(
                material=data['material'], defaults=data,
            )
            label = 'Created' if is_new else 'Exists '
            style = self.style.SUCCESS if is_new else self.style.WARNING
            self.stdout.write(f'  {style(label)}  {data["name"]} (${data["price"]})')
            if is_new:
                created += 1
        self.stdout.write(f'  -> {created} new, {len(CARD_PRODUCTS) - created} existing')

    # ───────────────────────────────────────────────────────
    def _seed_themes(self):
        from themes.models import Theme

        self.stdout.write(self.style.MIGRATE_HEADING('\n[4/6] Profile Themes'))
        created = 0
        for data in THEMES:
            _, is_new = Theme.objects.update_or_create(
                name=data['name'], defaults=data,
            )
            label = 'Created' if is_new else 'Exists '
            style = self.style.SUCCESS if is_new else self.style.WARNING
            self.stdout.write(f'  {style(label)}  {data["name"]}')
            if is_new:
                created += 1
        self.stdout.write(f'  -> {created} new, {len(THEMES) - created} existing')

    # ───────────────────────────────────────────────────────
    def _seed_payment_methods(self):
        from subscriptions.models import PaymentMethodSettings

        self.stdout.write(self.style.MIGRATE_HEADING('\n[5/6] Payment Methods'))
        created = 0
        for data in PAYMENT_METHODS:
            _, is_new = PaymentMethodSettings.objects.get_or_create(
                method=data['method'],
                defaults={
                    'display_name': data['display_name'],
                    'description': data['description'],
                    'is_enabled': data['is_enabled'],
                },
            )
            label = 'Created' if is_new else 'Exists '
            style = self.style.SUCCESS if is_new else self.style.WARNING
            self.stdout.write(f'  {style(label)}  {data["display_name"]}')
            if is_new:
                created += 1
        self.stdout.write(f'  -> {created} new, {len(PAYMENT_METHODS) - created} existing')

    # ───────────────────────────────────────────────────────
    def _seed_banking_details(self):
        from subscriptions.models import BankingDetail

        self.stdout.write(self.style.MIGRATE_HEADING('\n[6/6] Banking Details'))
        if BankingDetail.objects.exists():
            count = BankingDetail.objects.count()
            self.stdout.write(f'  {self.style.WARNING("Exists ")}  {count} bank account(s) already configured')
            return

        created = 0
        for data in BANKING_DETAILS:
            BankingDetail.objects.create(**data)
            self.stdout.write(f'  {self.style.SUCCESS("Created")}  {data["bank_name"]} - {data["account_number"]}')
            created += 1
        self.stdout.write(f'  -> {created} bank account(s) created')

    # ───────────────────────────────────────────────────────
    def _create_superuser(self):
        from accounts.models import User

        self.stdout.write(self.style.MIGRATE_HEADING('\n[+] Superuser Account'))

        if User.objects.filter(is_superuser=True).exists():
            admins = User.objects.filter(is_superuser=True).values_list('username', flat=True)
            self.stdout.write(f'  {self.style.WARNING("Exists ")}  Superuser(s): {", ".join(admins)}')
            return

        self.stdout.write('  No superuser found. Create one now?')
        answer = input('  Create superuser? [Y/n] ').strip().lower()
        if answer in ('n', 'no'):
            self.stdout.write(f'  {self.style.WARNING("Skipped")}  No superuser created')
            return

        try:
            username = input('  Username: ').strip()
            email = input('  Email: ').strip()
            password = getpass.getpass('  Password: ')
            password2 = getpass.getpass('  Password (confirm): ')

            if password != password2:
                self.stdout.write(self.style.ERROR('  Passwords do not match. Skipping.'))
                return

            if not username or not email or not password:
                self.stdout.write(self.style.ERROR('  All fields required. Skipping.'))
                return

            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            self.stdout.write(f'  {self.style.SUCCESS("Created")}  Superuser: {user.username} ({user.email})')
        except KeyboardInterrupt:
            self.stdout.write(f'\n  {self.style.WARNING("Skipped")}  Interrupted')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error creating superuser: {e}'))
