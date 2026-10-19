from django.contrib import admin

from .models import StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ["product", "warehouse", "kind", "quantity", "unit_cost", "source_number", "movement_date"]
