from django.contrib import admin

from .models import Workspace


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "owner", "currency", "vat_registered", "is_active", "created_at"]
    list_filter = ["is_active", "vat_registered", "currency"]
    search_fields = ["name", "slug", "kra_pin", "owner__email"]
    readonly_fields = ["created_at", "updated_at"]
