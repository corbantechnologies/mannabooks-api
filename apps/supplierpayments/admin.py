from django.contrib import admin

from .models import SupplierPayment


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ["number", "supplier", "payment_date", "amount", "withholding_amount", "status"]
