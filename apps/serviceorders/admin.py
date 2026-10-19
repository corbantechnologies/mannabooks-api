from django.contrib import admin

from .models import ServiceOrder


@admin.register(ServiceOrder)
class ServiceOrderAdmin(admin.ModelAdmin):
    list_display = ["number", "supplier", "order_date", "total", "status", "workspace"]
