from django.contrib import admin

from .models import StockTake


@admin.register(StockTake)
class StockTakeAdmin(admin.ModelAdmin):
    list_display = ["number", "warehouse", "count_date", "status", "difference_value"]
