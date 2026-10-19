from django.contrib import admin

from .models import PaymentVoucher


@admin.register(PaymentVoucher)
class PaymentVoucherAdmin(admin.ModelAdmin):
    list_display = ["number", "supplier", "voucher_date", "total", "status", "workspace"]
