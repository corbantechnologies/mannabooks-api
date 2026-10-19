from django.contrib import admin

from .models import Membership


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "workspace", "role", "status", "created_at"]
    list_filter = ["status", "role__slug"]
    search_fields = ["user__email", "user__full_name", "workspace__name"]
    raw_id_fields = ["user", "workspace", "role", "created_by"]
