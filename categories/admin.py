from django.contrib import admin
from .models import Category, RealEstateProperty, CreativeMedia, EventPackage, MenuItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon_color', 'icon_bg')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description', 'fields_config')}),
        ('Icon', {'fields': ('icon', 'icon_color', 'icon_bg'),
                  'description': 'SVG path markup and colors for the category card icon.'}),
    )


@admin.register(RealEstateProperty)
class RealEstatePropertyAdmin(admin.ModelAdmin):
    list_display = ('title', 'profile', 'price')


@admin.register(CreativeMedia)
class CreativeMediaAdmin(admin.ModelAdmin):
    list_display = ('title', 'profile', 'media_type')


@admin.register(EventPackage)
class EventPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'profile', 'price')


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'profile', 'price', 'category_label')
