from django.contrib import admin

from .models import ProductionOrder


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ["number", "bom", "quantity", "production_date", "status", "total_cost"]
