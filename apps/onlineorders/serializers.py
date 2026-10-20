from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount

from .models import OnlineOrder

M = {"max_digits": 18, "decimal_places": 2}


class OnlineOrderLineSerializer(serializers.Serializer):
    product_id = serializers.CharField()
    name = serializers.CharField()
    quantity = serializers.CharField()
    unit = serializers.CharField(allow_blank=True, required=False)
    unit_price = serializers.CharField(help_text="With VAT")
    total = serializers.CharField()


class PublicOrderSerializer(serializers.ModelSerializer):
    """What the customer sees on their order page (no internal details)."""

    lines = OnlineOrderLineSerializer(many=True, read_only=True)
    payment_status = serializers.CharField(read_only=True)
    shop_name = serializers.CharField(source="workspace.name", read_only=True)
    shop_phone = serializers.CharField(source="workspace.phone", read_only=True)

    class Meta:
        model = OnlineOrder
        fields = ["number", "token", "shop_name", "shop_phone", "customer_name", "phone", "fulfilment", "address", "lines", "subtotal", "delivery_fee",
                  "total", "status", "payment_method", "payment_status", "cancel_reason", "created_at"]
        read_only_fields = fields


class OnlineOrderSerializer(serializers.ModelSerializer):
    lines = OnlineOrderLineSerializer(many=True, read_only=True)
    payment_status = serializers.CharField(read_only=True)
    mpesa_receipt = serializers.CharField(source="mpesa_transaction.mpesa_receipt", read_only=True, default=None)
    receipt_id = serializers.UUIDField(read_only=True, allow_null=True)
    receipt_number = serializers.CharField(source="receipt.number", read_only=True, default=None)

    class Meta:
        model = OnlineOrder
        fields = ["id", "number", "token", "customer_name", "phone", "email", "fulfilment", "address", "notes", "lines", "subtotal", "delivery_fee",
                  "total", "status", "payment_method", "payment_status", "mpesa_receipt", "receipt_id", "receipt_number", "cancel_reason",
                  "completed_at", "created_at"]
        read_only_fields = fields


class PlaceLineSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)


class PlaceOrderSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    fulfilment = serializers.ChoiceField(choices=OnlineOrder.Fulfilment.choices)
    address = serializers.CharField(required=False, allow_blank=True, max_length=500)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    payment_method = serializers.ChoiceField(choices=OnlineOrder.PaymentMethod.choices)
    lines = PlaceLineSerializer(many=True)


class PayOrderSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, help_text="Blank: the order's phone")


class ShopProductSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    category = serializers.CharField(allow_blank=True)
    unit = serializers.CharField()
    price = serializers.DecimalField(**M, help_text="With VAT")
    image_url = serializers.CharField(allow_blank=True)
    available = serializers.BooleanField()


class ShopSerializer(serializers.Serializer):
    name = serializers.CharField()
    intro = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    email = serializers.CharField(allow_blank=True)
    address = serializers.CharField(allow_blank=True)
    logo_url = serializers.CharField(allow_blank=True)
    currency = serializers.CharField()
    allow_pickup = serializers.BooleanField()
    allow_delivery = serializers.BooleanField()
    delivery_fee = serializers.DecimalField(**M)
    pay_on_delivery = serializers.BooleanField()
    mpesa = serializers.BooleanField(help_text="Customers can pay by M-Pesa prompt when they order")
    products = ShopProductSerializer(many=True)


class OnlineOrderActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["confirm", "ready", "complete", "cancel", "request_payment"])
    method = serializers.ChoiceField(choices=["cash", "mpesa", "card", "bank"], required=False,
                                     help_text="Complete, when not paid by M-Pesa online: how the customer paid")
    payment_reference = serializers.CharField(required=False, allow_blank=True)
    deposit_account_id = WorkspaceRelatedField(LedgerAccount, source="deposit_account", required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)
