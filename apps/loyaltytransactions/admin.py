from django.contrib import admin

from .models import LoyaltyTransaction


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = ["member", "kind", "points", "remaining", "expires_on", "document_number"]
