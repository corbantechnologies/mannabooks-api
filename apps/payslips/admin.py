from django.contrib import admin

from .models import Payslip


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ["employee_name", "pay_run", "gross_pay", "paye", "net_pay"]
