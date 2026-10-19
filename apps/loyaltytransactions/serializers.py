from rest_framework import serializers

from .models import LoyaltyTransaction


class LoyaltyTransactionSerializer(serializers.ModelSerializer):
    member_id = serializers.UUIDField(source="member.id", read_only=True)
    customer_name = serializers.CharField(source="member.customer.name", read_only=True)

    class Meta:
        model = LoyaltyTransaction
        fields = ["id", "member_id", "customer_name", "kind", "points", "remaining", "expires_on", "document_type", "document_id",
                  "document_number", "description", "created_at"]
        read_only_fields = fields
