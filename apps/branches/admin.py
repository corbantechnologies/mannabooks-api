from django.contrib import admin

from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "workspace", "is_default", "is_active"]
    list_filter = ["is_default", "is_active"]
    search_fields = ["name", "code", "workspace__name"]
