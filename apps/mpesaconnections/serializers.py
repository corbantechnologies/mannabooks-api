from rest_framework import serializers

from apps.core.crypto import encrypt
from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount

from .models import MpesaConnection

SECRETS = {"consumer_key": "consumer_key_encrypted", "consumer_secret": "consumer_secret_encrypted", "passkey": "passkey_encrypted"}


class MpesaConnectionSerializer(serializers.ModelSerializer):
    consumer_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    consumer_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    passkey = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_credentials = serializers.SerializerMethodField()
    deposit_account_id = WorkspaceRelatedField(LedgerAccount, source="deposit_account", allow_null=True, required=False)

    class Meta:
        model = MpesaConnection
        fields = [
            "id", "environment", "shortcode_type", "shortcode", "till_number", "consumer_key", "consumer_secret", "passkey",
            "has_credentials", "deposit_account_id", "is_active", "verified_at", "c2b_registered_at", "last_error",
        ]
        read_only_fields = ["id", "has_credentials", "verified_at", "c2b_registered_at", "last_error"]

    def get_has_credentials(self, obj) -> bool:
        return all(getattr(obj, f) for f in SECRETS.values())

    def validate_shortcode(self, value):
        value = value.strip()
        if not value.isdigit():
            raise serializers.ValidationError("Use digits only.")
        return value

    def validate(self, attrs):
        for field, stored in SECRETS.items():
            value = attrs.pop(field, None)
            if value:
                attrs[stored] = encrypt(value.strip())
        kind = attrs.get("shortcode_type", getattr(self.instance, "shortcode_type", "paybill"))
        if kind == "till" and not attrs.get("till_number", getattr(self.instance, "till_number", "")):
            raise serializers.ValidationError({"till_number": ["Enter the till number customers pay to."]})
        account = attrs.get("deposit_account")
        if account is not None and account.subtype not in ("cash", "bank"):
            raise serializers.ValidationError({"deposit_account_id": ["Choose a bank or M-Pesa account."]})
        if attrs.get("is_active"):
            merged = {f: attrs.get(s, getattr(self.instance, s, "") if self.instance else "") for f, s in SECRETS.items()}
            if not all(merged.values()):
                raise serializers.ValidationError({"is_active": ["Enter the consumer key, consumer secret and passkey first."]})
        return attrs
