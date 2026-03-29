from django.contrib import admin
from .models import TapEvent, ProfileEvent


@admin.register(TapEvent)
class TapEventAdmin(admin.ModelAdmin):
    list_display = ('profile', 'timestamp', 'ip_address', 'country')
    list_filter = ('timestamp',)
    search_fields = ('profile__user__username',)
    readonly_fields = ('profile', 'timestamp', 'ip_address', 'user_agent', 'country')


@admin.register(ProfileEvent)
class ProfileEventAdmin(admin.ModelAdmin):
    list_display = ('profile', 'event_type', 'item_title', 'timestamp', 'ip_address')
    list_filter = ('event_type', 'timestamp')
    search_fields = ('profile__user__username', 'item_title')
    readonly_fields = ('profile', 'event_type', 'item_id', 'item_title', 'timestamp', 'ip_address')
