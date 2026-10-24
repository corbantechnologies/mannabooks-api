from django.utils import timezone
from rest_framework import serializers

from apps.core.dimensions import DimensionFields
from apps.core.fields import WorkspaceRelatedField
from apps.core.sales_serializers import SALES_DOCUMENT_FIELDS, SALES_READ_ONLY, SalesLineSerializer
from apps.customers.models import Customer

from .models import Quotation


class QuotationSerializer(DimensionFields, serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer")
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    lines = SalesLineSerializer(many=True, required=False)
    is_expired = serializers.SerializerMethodField()
    invoice_id = serializers.SerializerMethodField()
    catalogue_id = serializers.UUIDField(read_only=True, allow_null=True)
    catalogue_name = serializers.CharField(source="catalogue.name", read_only=True, default=None)
    public_url = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = SALES_DOCUMENT_FIELDS + ["status", "valid_until", "is_expired", "invoice_id", "catalogue_id", "catalogue_name",
                                          "public_url", "contact_email"]
        read_only_fields = SALES_READ_ONLY + ["status", "is_expired", "invoice_id", "catalogue_id", "catalogue_name", "public_url"]
        extra_kwargs = {"currency": {"required": False}, "issue_date": {"required": False}, "valid_until": {"required": False}}

    def get_is_expired(self, obj) -> bool:
        return obj.status in ("draft", "sent") and obj.valid_until < timezone.localdate()

    def get_public_url(self, obj) -> str | None:
        from apps.catalogues.services import public_url

        return public_url(obj)

    def get_invoice_id(self, obj) -> str | None:
        invoice = obj.invoices.order_by("-created_at").first()
        return str(invoice.id) if invoice else None


class QuotationActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["send", "accept", "decline", "reopen"])


class ConvertedSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField()


class ShareLinkSerializer(serializers.Serializer):
    url = serializers.CharField()
