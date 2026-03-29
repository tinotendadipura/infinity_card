from django.contrib import admin
from .models import Profile, SocialLink, CatalogCategory, CatalogItem, CatalogItemImage, Service, HomepageTestimonial


class SocialLinkInline(admin.TabularInline):
    model = SocialLink
    extra = 1


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'user', 'category', 'is_published', 'updated_at')
    list_filter = ('is_published', 'category')
    search_fields = ('display_name', 'user__username')
    raw_id_fields = ('user',)
    inlines = [SocialLinkInline]


@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ('profile', 'platform', 'url', 'order')
    list_filter = ('platform',)
    search_fields = ('profile__user__username',)


class CatalogItemImageInline(admin.TabularInline):
    model = CatalogItemImage
    extra = 1


@admin.register(CatalogCategory)
class CatalogCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'profile', 'order')
    search_fields = ('name', 'profile__display_name')
    list_editable = ('order',)


@admin.register(CatalogItem)
class CatalogItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'profile', 'category', 'price', 'order')
    list_filter = ('category',)
    search_fields = ('title', 'profile__display_name')
    inlines = [CatalogItemImageInline]


@admin.register(CatalogItemImage)
class CatalogItemImageAdmin(admin.ModelAdmin):
    list_display = ('item', 'order')
    search_fields = ('item__title',)
    raw_id_fields = ('item',)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('title', 'profile', 'icon', 'price', 'order')
    list_filter = ('icon',)
    search_fields = ('title', 'profile__display_name')
    list_editable = ('order',)


@admin.register(HomepageTestimonial)
class HomepageTestimonialAdmin(admin.ModelAdmin):
    list_display = ('author_name', 'author_role', 'author_company', 'rating', 'is_active', 'order', 'created_at')
    list_filter = ('is_active', 'rating', 'created_at')
    search_fields = ('author_name', 'author_company', 'content')
    list_editable = ('is_active', 'order', 'rating')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Author Information', {
            'fields': ('author_name', 'author_role', 'author_company', 'author_photo')
        }),
        ('Testimonial Content', {
            'fields': ('content', 'rating')
        }),
        ('Display Settings', {
            'fields': ('is_active', 'order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
