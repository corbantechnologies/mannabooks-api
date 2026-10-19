from django.conf import settings
from rest_framework import serializers

from apps.core.crypto import encrypt

from .models import EtimsDevice


class EtimsDeviceSerializer(serializers.ModelSerializer):
    communication_key = serializers.CharField(write_only=True, required=False, allow_blank=True,
                                              help_text="Stored encrypted and never shown again")
    has_communication_key = serializers.SerializerMethodField()
    platform_enabled = serializers.SerializerMethodField(help_text="eTIMS signing is switched on for the whole platform")

    class Meta:
        model = EtimsDevice
        fields = [
            "id", "kra_pin", "branch_code", "device_serial", "environment", "communication_key", "has_communication_key",
            "sdc_id", "mrc_no", "last_invoice_number", "is_active", "initialised_at", "platform_enabled",
        ]
        read_only_fields = ["id", "has_communication_key", "sdc_id", "mrc_no", "last_invoice_number", "initialised_at", "platform_enabled"]

    def get_has_communication_key(self, obj) -> bool:
        return bool(obj.communication_key_encrypted)

    def get_platform_enabled(self, obj) -> bool:
        return settings.ETIMS_ENABLED

    def validate_kra_pin(self, value):
        value = value.strip().upper()
        if len(value) != 11 or not value[0].isalpha() or not value[-1].isalpha() or not value[1:-1].isdigit():
            raise serializers.ValidationError("A KRA PIN looks like A123456789B.")
        return value

    def validate(self, attrs):
        key = attrs.pop("communication_key", None)
        if key:
            attrs["communication_key_encrypted"] = encrypt(key.strip())
        if attrs.get("is_active") and not (key or (self.instance and self.instance.communication_key_encrypted)):
            raise serializers.ValidationError({"is_active": ["Connect to KRA first, so MannaBooks has the communication key."]})
        return attrs
