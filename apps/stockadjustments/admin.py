from django.contrib import admin

from .models import StockAdjustment


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ["number", "warehouse", "adjustment_date", "reason", "total_value", "status"]
