from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.invoices.models import Invoice

from .models import PortalLink


class PortalLinkSerializer(serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer")
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_id = WorkspaceRelatedField(Invoice, source="invoice", allow_null=True, required=False)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default=None)
    url = serializers.CharField(read_only=True)
    days = serializers.IntegerField(write_only=True, required=False, min_value=1, max_value=365, default=30,
                                    help_text="How long the link works")
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = PortalLink
        fields = ["id", "customer_id", "customer_name", "invoice_id", "invoice_number", "url", "days", "expires_at", "revoked_at",
                  "view_count", "last_viewed_at", "is_active", "created_at"]
        read_only_fields = ["id", "customer_name", "invoice_number", "url", "expires_at", "revoked_at", "view_count", "last_viewed_at", "created_at"]

    def get_is_active(self, obj) -> bool:
        from django.utils import timezone

        return not obj.revoked_at and not (obj.expires_at and obj.expires_at < timezone.now())

    def validate(self, attrs):
        invoice = attrs.get("invoice")
        if invoice is not None:
            if invoice.customer_id != attrs["customer"].id:
                raise serializers.ValidationError({"invoice_id": ["That invoice belongs to another customer."]})
            if invoice.status in ("draft", "void"):
                raise serializers.ValidationError({"invoice_id": ["Only issued invoices can be shared."]})
        return attrs


class PortalPaySerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    phone = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
