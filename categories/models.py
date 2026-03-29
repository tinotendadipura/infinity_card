from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    fields_config = models.JSONField(
        default=dict,
        help_text='Defines enabled sections for this category template',
    )
    icon = models.TextField(
        blank=True,
        help_text='SVG inner markup (path elements) for the category icon',
    )
    icon_color = models.CharField(
        max_length=30, blank=True,
        help_text='CSS color for the icon SVG stroke, e.g. #A5B4FC',
    )
    icon_bg = models.CharField(
        max_length=60, blank=True,
        help_text='CSS background for icon container, e.g. rgba(99,102,241,.15)',
    )

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class RealEstateProperty(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile', on_delete=models.CASCADE, related_name='properties',
    )
    title = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    bedrooms = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='categories/real_estate/', blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'real estate properties'

    def __str__(self):
        return self.title


class CreativeMedia(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile', on_delete=models.CASCADE, related_name='media_items',
    )
    title = models.CharField(max_length=200)
    media_type = models.CharField(
        max_length=10,
        choices=[('image', 'Image'), ('video', 'Video')],
    )
    file = models.FileField(upload_to='categories/creative/', blank=True)
    url = models.URLField(blank=True, help_text='External embed URL (YouTube, Vimeo)')
    caption = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'creative media'

    def __str__(self):
        return self.title


class EventPackage(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile', on_delete=models.CASCADE, related_name='event_packages',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='categories/events/', blank=True)

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    profile = models.ForeignKey(
        'profiles.Profile', on_delete=models.CASCADE, related_name='menu_items',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    category_label = models.CharField(
        max_length=50, blank=True,
        help_text='e.g., Starters, Mains, Desserts',
    )
    image = models.ImageField(upload_to='categories/restaurant/', blank=True)

    def __str__(self):
        return self.name
