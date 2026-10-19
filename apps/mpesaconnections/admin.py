from django.contrib import admin

from .models import MpesaConnection


@admin.register(MpesaConnection)
class MpesaConnectionAdmin(admin.ModelAdmin):
    list_display = ["workspace", "shortcode_type", "shortcode", "environment", "is_active"]
    exclude = ["consumer_key_encrypted", "consumer_secret_encrypted", "passkey_encrypted"]
