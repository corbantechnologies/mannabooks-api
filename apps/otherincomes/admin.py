from django.contrib import admin

from .models import OtherIncome


@admin.register(OtherIncome)
class OtherIncomeAdmin(admin.ModelAdmin):
    list_display = ["number", "income_date", "payer", "received_into", "total", "status"]
