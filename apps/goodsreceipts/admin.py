from django.contrib import admin

from .models import GoodsReceipt


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ["number", "supplier", "receipt_date", "total_value", "status", "workspace"]
