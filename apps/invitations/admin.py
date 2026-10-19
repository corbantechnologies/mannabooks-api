from django.contrib import admin

from .models import Invitation


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "workspace", "role", "status", "expires_at", "created_at"]
    list_filter = ["status"]
    search_fields = ["email", "workspace__name"]
    readonly_fields = ["token", "accepted_by", "accepted_at"]
