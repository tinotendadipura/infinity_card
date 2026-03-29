from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.subject} – {self.name} ({self.created_at:%Y-%m-%d})'


class BlogPost(models.Model):
    CATEGORY_CHOICES = [
        ('nfc', 'NFC Technology'),
        ('networking', 'Networking'),
        ('business', 'Business Tips'),
        ('product', 'Product Updates'),
        ('guides', 'How-To Guides'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='blog_posts',
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='nfc')
    cover_image = models.ImageField(upload_to='blog/', blank=True)
    excerpt = models.CharField(max_length=300, blank=True, help_text='Short summary shown on the listing page')
    body = models.TextField(help_text='Full article content (HTML allowed)')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    is_featured = models.BooleanField(default=False, help_text='Pin to the top of the blog')
    views_count = models.PositiveIntegerField(default=0, editable=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @property
    def reading_time(self):
        word_count = len(self.body.split())
        minutes = max(1, round(word_count / 200))
        return minutes

    @property
    def comments_count(self):
        return self.comments.count()


class BlogImage(models.Model):
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='blog/images/')
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'Image for "{self.post.title}" ({self.pk})'


class VideoTestimonial(models.Model):
    """Video testimonial displayed on the homepage spotlight carousel."""
    VIDEO_SOURCE_CHOICES = [
        ('upload', 'Upload Video'),
        ('link', 'External Link'),
    ]

    name = models.CharField(max_length=100, help_text='Reviewer name (e.g. "Daniel M.")')
    review = models.TextField(help_text='Review text shown in the modal')
    rating = models.PositiveSmallIntegerField(default=5, help_text='Star rating 1-5')
    date_label = models.CharField(max_length=20, blank=True, help_text='Display date (e.g. "02/2026")')
    thumbnail = models.ImageField(upload_to='testimonials/thumbnails/', help_text='Portrait thumbnail image for the carousel slide')
    video_source = models.CharField(max_length=10, choices=VIDEO_SOURCE_CHOICES, default='upload')
    video_file = models.FileField(upload_to='testimonials/videos/', blank=True, help_text='Upload an MP4 video file')
    video_url = models.URLField(blank=True, help_text='External video URL (YouTube, Vimeo, etc.)')
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=True, help_text='Show verified badge')
    sort_order = models.PositiveIntegerField(default=0, help_text='Lower numbers appear first')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return f'{self.name} - {self.rating} stars'

    @property
    def has_video(self):
        if self.video_source == 'upload':
            return bool(self.video_file)
        return bool(self.video_url)

    @property
    def video_display_url(self):
        """Return the URL to use for playing the video."""
        if self.video_source == 'upload' and self.video_file:
            return self.video_file.url
        if self.video_source == 'link' and self.video_url:
            return self.video_url
        return ''

    @property
    def stars_html(self):
        return '&#9733;' * self.rating + '&#9734;' * (5 - self.rating)


class PartnerLogo(models.Model):
    """Partner/client logo displayed on the homepage."""
    name = models.CharField(max_length=100, help_text='Company or partner name')
    logo = models.ImageField(upload_to='partners/', help_text='Logo image (PNG recommended, transparent background)')
    website_url = models.URLField(blank=True, help_text='Optional link to partner website')
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0, help_text='Lower numbers appear first')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class BlogComment(models.Model):
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='comments')
    author_name = models.CharField(max_length=100)
    author_email = models.EmailField()
    body = models.TextField()
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.author_name} on "{self.post.title}"'
