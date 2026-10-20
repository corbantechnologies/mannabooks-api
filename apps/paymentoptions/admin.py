from django.contrib import admin

from .models import PaymentOption


@admin.register(PaymentOption)
class PaymentOptionAdmin(admin.ModelAdmin):
    list_display = ("kind", "number", "account_number", "workspace", "show_on_documents")
