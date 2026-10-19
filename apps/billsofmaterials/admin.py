from django.contrib import admin

from .models import BillOfMaterials


@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    list_display = ["product", "name", "output_quantity", "is_active", "workspace"]
