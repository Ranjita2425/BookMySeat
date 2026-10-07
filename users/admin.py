from django.contrib import admin
from .models import Location, UserProfile

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("city", "district", "state")
    list_filter = ("state", "district")
    search_fields = ("city", "district", "state")

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "preferred_location")
    list_filter = ("preferred_location__state",)
    search_fields = ("user__username",)