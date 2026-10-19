from django.contrib import admin

from .models import Role


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["name", "workspace", "is_preset", "created_at"]
    list_filter = ["is_preset"]
    search_fields = ["name", "workspace__name"]
