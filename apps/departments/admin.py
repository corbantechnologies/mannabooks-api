from django.contrib import admin

from .models import Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "workspace", "head", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "workspace__name"]
    raw_id_fields = ["head", "workspace", "created_by"]
