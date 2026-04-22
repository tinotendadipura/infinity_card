import io
import os
import secrets
import string

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from PIL import Image


def generate_profile_code():
    """Generate a random 7-char lowercase alphanumeric code for NFC URLs."""
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(7))


COVER_MAX_W = 1200
COVER_MAX_H = 600
COVER_QUALITY = 85


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    category = models.ForeignKey(
        'categories.Category',
        on_delete=models.SET_NULL,
        null=True,
    )
    display_name = models.CharField(max_length=100)
    headline = models.CharField(max_length=200, blank=True)
    bio = models.TextField(blank=True)
    profile_image = models.ImageField(upload_to='profiles/', blank=True)
    cover_image = models.ImageField(upload_to='covers/', blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True, help_text='Public contact email')
    location = models.CharField(max_length=150, blank=True)
    website_url = models.URLField(blank=True)
    theme = models.ForeignKey(
        'themes.Theme',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    color_bg = models.CharField(max_length=7, default='#F8FAFB', blank=True)
    color_primary = models.CharField(max_length=7, default='#2EC4B6', blank=True)
    color_secondary = models.CharField(max_length=7, default='#6B2FA0', blank=True)
    color_text = models.CharField(max_length=7, default='#1E293B', blank=True)
    color_btn = models.CharField(max_length=7, default='#2EC4B6', blank=True)
    color_btn_text = models.CharField(max_length=7, default='#FFFFFF', blank=True)
    is_published = models.BooleanField(default=False)

    # Physical NFC card images
    card_front_image = models.ImageField(upload_to='cards/', blank=True, help_text='Photo of the front of your NFC card')
    card_back_image = models.ImageField(upload_to='cards/', blank=True, help_text='Photo of the back of your NFC card')

    # Feature toggles — control which sections appear on the public profile
    show_catalog = models.BooleanField(default=True, help_text='Show Products / Catalog section')
    show_social_links = models.BooleanField(default=True, help_text='Show social media links')
    show_contact_info = models.BooleanField(default=True, help_text='Show phone, email, location')
    show_bio = models.BooleanField(default=True, help_text='Show About / Bio section')
    show_contact_form = models.BooleanField(default=False, help_text='Show a contact form on profile')
    show_business_hours = models.BooleanField(default=False, help_text='Show business hours section')
    show_gallery = models.BooleanField(default=False, help_text='Show photo gallery section')
    show_skills = models.BooleanField(default=False, help_text='Show skills / expertise section')
    show_experience = models.BooleanField(default=False, help_text='Show work experience section')
    show_education = models.BooleanField(default=False, help_text='Show education section')
    show_services = models.BooleanField(default=False, help_text='Show services section')
    show_testimonials = models.BooleanField(default=False, help_text='Show testimonials / reviews')
    show_map = models.BooleanField(default=False, help_text='Show location map on profile')
    show_website_portfolio = models.BooleanField(default=False, help_text='Show website portfolio section')

    # Map / location coordinates
    map_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    map_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    map_location_label = models.CharField(max_length=255, blank=True, help_text='Friendly address shown on the map')

    # Unique NFC card URL code
    profile_code = models.CharField(
        max_length=10, unique=True, blank=True, default=generate_profile_code,
        help_text='Unique code used in the NFC card subdomain URL',
    )

    # Auto-generated QR code pointing to the user's NFC URL
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, help_text='Auto-generated QR code for NFC card')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.display_name} ({self.user.username})'

    def get_absolute_url(self):
        """Return public profile URL: /p/<username>/<code>/"""
        return f'/p/{self.user.username}/{self.profile_code}/'

    @property
    def nfc_url(self):
        """Full NFC card URL using username and profile code."""
        return f'/p/{self.user.username}/{self.profile_code}/'

    @property
    def production_nfc_url(self):
        """Production NFC URL. Used for QR codes."""
        return f'https://inftycard.cc/p/{self.user.username}/{self.profile_code}/'

    @property
    def nfc_subdomain(self):
        """Deprecated: kept for backward compatibility. Returns path portion."""
        return f'/p/{self.user.username}/{self.profile_code}/'

    def generate_qr_code(self):
        """Generate a QR code PNG pointing to this profile's NFC URL."""
        import qrcode

        url = self.production_nfc_url
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='#0F172A', back_color='#FFFFFF').convert('RGB')

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)

        filename = f'qr_{self.user.username}_{self.profile_code}.png'
        self.qr_code.save(filename, ContentFile(buf.read()), save=False)

    def save(self, *args, **kwargs):
        if not self.profile_code:
            self.profile_code = generate_profile_code()

        # Generate QR code on first save or if missing
        generate_qr = not self.qr_code and self.pk is not None
        is_new = self.pk is None

        super().save(*args, **kwargs)

        if is_new or generate_qr:
            self.generate_qr_code()
            Profile.objects.filter(pk=self.pk).update(qr_code=self.qr_code.name)

        if self.cover_image:
            self._optimize_cover()

    def _optimize_cover(self):
        """Resize cover to max 1200×600 and convert to WebP for performance."""
        try:
            img = Image.open(self.cover_image.path)
        except Exception:
            return

        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        w, h = img.size
        if w > COVER_MAX_W or h > COVER_MAX_H:
            img.thumbnail((COVER_MAX_W, COVER_MAX_H), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format='WEBP', quality=COVER_QUALITY, method=4)
        buf.seek(0)

        new_name = os.path.splitext(os.path.basename(self.cover_image.name))[0] + '.webp'
        self.cover_image.save(new_name, ContentFile(buf.read()), save=False)
        # save=False above avoids recursion; persist the new filename
        Profile.objects.filter(pk=self.pk).update(cover_image=self.cover_image.name)


class SocialLink(models.Model):
    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('twitter', 'X / Twitter'),
        ('linkedin', 'LinkedIn'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
        ('github', 'GitHub'),
        ('whatsapp', 'WhatsApp'),
        ('telegram', 'Telegram'),
        ('snapchat', 'Snapchat'),
        ('pinterest', 'Pinterest'),
        ('other', 'Other'),
    ]

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='social_links',
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    url = models.URLField()
    label = models.CharField(max_length=50, blank=True, help_text='Custom label (optional)')
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'platform']

    def __str__(self):
        return f'{self.get_platform_display()} – {self.profile}'


class CatalogCategory(models.Model):
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='catalog_categories',
    )
    name = models.CharField(max_length=80)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'catalog categories'

    def __str__(self):
        return f'{self.name} – {self.profile}'


class CatalogItem(models.Model):
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='catalog_items',
    )
    category = models.ForeignKey(
        CatalogCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='items',
    )
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    price = models.CharField(max_length=50, blank=True, help_text='e.g. $25, From $100, Free')
    image = models.ImageField(upload_to='catalog/')
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return f'{self.title} – {self.profile}'


class CatalogItemImage(models.Model):
    item = models.ForeignKey(
        CatalogItem, on_delete=models.CASCADE, related_name='extra_images',
    )
    image = models.ImageField(upload_to='catalog/')
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'Image for {self.item.title}'


class Service(models.Model):
    ICON_CHOICES = [
        ('briefcase', 'Briefcase'),
        ('code', 'Code'),
        ('paint', 'Design'),
        ('camera', 'Photography'),
        ('chart', 'Analytics'),
        ('globe', 'Web'),
        ('megaphone', 'Marketing'),
        ('wrench', 'Maintenance'),
        ('shield', 'Security'),
        ('heart', 'Health'),
        ('book', 'Education'),
        ('truck', 'Delivery'),
        ('home', 'Real Estate'),
        ('music', 'Music'),
        ('film', 'Video'),
        ('star', 'Premium'),
        ('zap', 'Lightning'),
        ('users', 'Consulting'),
    ]

    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='services',
    )
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=500)
    price = models.CharField(max_length=50, blank=True, help_text='e.g. $50/hr, From $200, Free consultation')
    icon = models.CharField(max_length=20, choices=ICON_CHOICES, default='briefcase')
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return f'{self.title} – {self.profile}'


class Skill(models.Model):
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='skills',
    )
    name = models.CharField(max_length=100)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        unique_together = [('profile', 'name')]

    def __str__(self):
        return f'{self.name} – {self.profile}'


class Experience(models.Model):
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='experiences',
    )
    title = models.CharField(max_length=150, help_text='Job title or role')
    company = models.CharField(max_length=150)
    location = models.CharField(max_length=150, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text='Leave blank if current')
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True, max_length=2000)
    company_logo = models.ImageField(upload_to='experience_logos/', blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', '-start_date']

    def __str__(self):
        return f'{self.title} at {self.company} – {self.profile}'

    def duration_display(self):
        """Return a human-readable duration string like '2 yrs 3 mos'."""
        from django.utils import timezone
        end = self.end_date or timezone.now().date()
        total_months = (end.year - self.start_date.year) * 12 + (end.month - self.start_date.month)
        if total_months < 0:
            total_months = 0
        years = total_months // 12
        months = total_months % 12
        parts = []
        if years:
            parts.append(f'{years} yr{"s" if years != 1 else ""}')
        if months:
            parts.append(f'{months} mo{"s" if months != 1 else ""}')
        return ' '.join(parts) or 'Less than a month'


class Education(models.Model):
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='education_entries',
    )
    school = models.CharField(max_length=200)
    degree = models.CharField(max_length=200, blank=True, help_text='e.g. Bachelor of Science')
    field_of_study = models.CharField(max_length=200, blank=True, help_text='e.g. Computer Science')
    start_year = models.PositiveSmallIntegerField(null=True, blank=True)
    end_year = models.PositiveSmallIntegerField(null=True, blank=True)
    description = models.TextField(blank=True, max_length=1000)
    school_logo = models.ImageField(upload_to='education_logos/', blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', '-start_year']
        verbose_name_plural = 'education entries'

    def __str__(self):
        return f'{self.school} – {self.profile}'


class GalleryImage(models.Model):
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='gallery_images',
    )
    image = models.ImageField(upload_to='gallery/')
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return f'Gallery image {self.pk} – {self.profile}'


class BusinessHour(models.Model):
    DAY_CHOICES = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'),
        (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
    ]
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='business_hours',
    )
    day = models.PositiveSmallIntegerField(choices=DAY_CHOICES)
    opening_time = models.TimeField()
    closing_time = models.TimeField()
    is_closed = models.BooleanField(default=False, help_text='Mark as closed for this day')

    class Meta:
        ordering = ['day']
        unique_together = ('profile', 'day')

    def __str__(self):
        return f'{self.get_day_display()} – {self.profile}'


class Testimonial(models.Model):
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='testimonials',
    )
    author_name = models.CharField(max_length=150)
    author_role = models.CharField(max_length=150, blank=True, help_text='e.g. CEO at Acme Inc.')
    author_photo = models.ImageField(upload_to='testimonials/', blank=True)
    content = models.TextField(max_length=1000)
    rating = models.PositiveSmallIntegerField(default=5, help_text='1-5 star rating')
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return f'Testimonial by {self.author_name} – {self.profile}'


class ContactMessage(models.Model):
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='contact_messages',
    )
    sender_name = models.CharField(max_length=150)
    sender_email = models.EmailField()
    sender_phone = models.CharField(max_length=30)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField(max_length=2000, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.sender_name} – {self.sender_phone}'


class WebsitePortfolio(models.Model):
    profile = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name='website_portfolios',
    )
    url = models.URLField(help_text='Full URL of the website to showcase')
    title = models.CharField(max_length=200, help_text='Project or website name')
    description = models.CharField(max_length=500, blank=True, help_text='Brief description')
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return f'{self.title} – {self.profile}'

    @property
    def domain(self):
        from urllib.parse import urlparse
        return urlparse(self.url).netloc


class HomepageTestimonial(models.Model):
    """Testimonials displayed on the homepage, managed by admin"""
    author_name = models.CharField(max_length=150)
    author_role = models.CharField(max_length=150, help_text='e.g. CEO at Acme Inc.')
    author_company = models.CharField(max_length=150, blank=True)
    author_photo = models.ImageField(upload_to='homepage/testimonials/', help_text='Profile photo of the author')
    content = models.TextField(max_length=1000, help_text='Testimonial content')
    rating = models.PositiveSmallIntegerField(default=5, help_text='1-5 star rating')
    is_active = models.BooleanField(default=True, help_text='Show on homepage')
    order = models.PositiveSmallIntegerField(default=0, help_text='Display order')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', '-created_at']
        verbose_name = 'Homepage Testimonial'
        verbose_name_plural = 'Homepage Testimonials'

    def __str__(self):
        return f'Testimonial by {self.author_name}'

    def star_rating(self):
        """Return star rating as HTML"""
        stars = '★' * self.rating + '☆' * (5 - self.rating)
        return stars
