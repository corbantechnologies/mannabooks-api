from django.contrib import admin

from .models import PayRun


@admin.register(PayRun)
class PayRunAdmin(admin.ModelAdmin):
    list_display = ["year", "month", "status", "gross_pay", "net_pay", "workspace"]
