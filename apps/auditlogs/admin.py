from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "workspace", "actor", "action", "model", "object_repr"]
    list_filter = ["action", "model"]
    search_fields = ["object_repr", "object_id", "actor__email"]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
