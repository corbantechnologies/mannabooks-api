from django.contrib import admin

from .models import EtimsDevice


@admin.register(EtimsDevice)
class EtimsDeviceAdmin(admin.ModelAdmin):
    list_display = ["workspace", "kra_pin", "device_serial", "environment", "is_active", "last_invoice_number"]
    list_filter = ["environment", "is_active"]
    exclude = ["communication_key_encrypted"]
