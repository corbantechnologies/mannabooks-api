from django.contrib import admin

from .models import BankTransfer


@admin.register(BankTransfer)
class BankTransferAdmin(admin.ModelAdmin):
    list_display = ["number", "transfer_date", "from_account", "to_account", "amount", "status"]
