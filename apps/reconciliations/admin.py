from django.contrib import admin

from .models import Reconciliation


@admin.register(Reconciliation)
class ReconciliationAdmin(admin.ModelAdmin):
    list_display = ["bank_account", "statement_date", "statement_balance", "status"]
