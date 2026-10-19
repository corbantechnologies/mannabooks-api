from django.contrib import admin

from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["number", "name", "phone", "kra_pin", "workspace", "is_active"]
