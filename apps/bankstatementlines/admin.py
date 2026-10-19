from django.contrib import admin

from .models import BankStatementLine


@admin.register(BankStatementLine)
class BankStatementLineAdmin(admin.ModelAdmin):
    list_display = ["bank_account", "line_date", "description", "amount", "status"]
