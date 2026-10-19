from django.contrib import admin

from .models import Receipt


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ["number", "customer_name", "issue_date", "total", "method", "status", "workspace"]
    list_filter = ["status", "method"]
    search_fields = ["number", "customer_name", "payment_reference", "workspace__name"]
