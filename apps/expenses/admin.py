from django.contrib import admin

from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["number", "expense_date", "payee", "paid_from", "total", "status"]
