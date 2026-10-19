from django.contrib import admin

from .models import Bill


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ["number", "supplier", "supplier_invoice_number", "bill_date", "total", "balance_due", "status"]
