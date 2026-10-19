from rest_framework import serializers

from .models import LoyaltyProgram


class LoyaltyProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltyProgram
        fields = ["id", "name", "is_active", "spend_per_point", "point_value", "min_redeem_points", "max_redeem_percent",
                  "expiry_months", "earn_on_invoices"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        for field in ("spend_per_point", "point_value"):
            if field in attrs and attrs[field] <= 0:
                raise serializers.ValidationError({field: ["Must be more than zero."]})
        if attrs.get("max_redeem_percent", 1) > 100:
            raise serializers.ValidationError({"max_redeem_percent": ["Can't be more than 100%."]})
        return attrs
