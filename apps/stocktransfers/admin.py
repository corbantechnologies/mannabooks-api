from django.contrib import admin

from .models import StockTransfer


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ["number", "from_warehouse", "to_warehouse", "transfer_date", "status"]
