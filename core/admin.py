from django.contrib import admin
from django.utils import timezone
from .models import ContactMessage, BlogPost, PartnerLogo, VideoTestimonial


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'name', 'email', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message')
    readonly_fields = ('name', 'email', 'subject', 'message', 'created_at')
    actions = ['mark_read', 'mark_unread']

    def mark_read(self, request, queryset):
        queryset.update(is_read=True)
    mark_read.short_description = 'Mark selected as read'

    def mark_unread(self, request, queryset):
        queryset.update(is_read=False)
    mark_unread.short_description = 'Mark selected as unread'


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'status', 'is_featured', 'views_count', 'published_at')
    list_filter = ('status', 'category', 'is_featured', 'published_at')
    search_fields = ('title', 'excerpt', 'body')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('status', 'is_featured', 'category')
    date_hierarchy = 'published_at'
    ordering = ('-published_at', '-created_at')
    readonly_fields = ('views_count', 'created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('title', 'slug', 'author', 'category', 'status', 'is_featured'),
        }),
        ('Content', {
            'fields': ('cover_image', 'excerpt', 'body'),
        }),
        ('Metadata', {
            'fields': ('published_at', 'views_count', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    actions = ['publish_posts']

    def publish_posts(self, request, queryset):
        queryset.update(status='published', published_at=timezone.now())
    publish_posts.short_description = 'Publish selected posts'

    def save_model(self, request, obj, form, change):
        if not obj.author_id:
            obj.author = request.user
        if obj.status == 'published' and not obj.published_at:
            obj.published_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(PartnerLogo)
class PartnerLogoAdmin(admin.ModelAdmin):
    list_display = ('name', 'website_url', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name',)
    list_editable = ('is_active', 'sort_order')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(VideoTestimonial)
class VideoTestimonialAdmin(admin.ModelAdmin):
    list_display = ('name', 'rating', 'is_active', 'is_verified', 'sort_order', 'created_at')
    list_filter = ('is_active', 'is_verified', 'rating', 'created_at')
    search_fields = ('name', 'review')
    list_editable = ('is_active', 'sort_order', 'rating')
    readonly_fields = ('created_at', 'updated_at')
