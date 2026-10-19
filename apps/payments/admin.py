from django.contrib import admin

from .models import Payment, PaymentAllocation


class AllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    raw_id_fields = ["invoice"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["number", "customer", "payment_date", "amount", "method", "status", "workspace"]
    list_filter = ["status", "method"]
    search_fields = ["number", "reference", "customer__name", "workspace__name"]
    inlines = [AllocationInline]
