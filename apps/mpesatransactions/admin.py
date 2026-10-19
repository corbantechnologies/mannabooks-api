from django.contrib import admin

from .models import MpesaTransaction


@admin.register(MpesaTransaction)
class MpesaTransactionAdmin(admin.ModelAdmin):
    list_display = ["mpesa_receipt", "kind", "status", "amount", "phone", "workspace", "created_at"]
    list_filter = ["kind", "status"]
    search_fields = ["mpesa_receipt", "phone", "account_reference"]
