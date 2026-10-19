from django.contrib import admin

from .models import CostCenter


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "workspace", "is_active")
