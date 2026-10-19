from django.contrib import admin

from .models import PortalLink


@admin.register(PortalLink)
class PortalLinkAdmin(admin.ModelAdmin):
    list_display = ["customer", "invoice", "expires_at", "revoked_at", "view_count", "workspace"]
