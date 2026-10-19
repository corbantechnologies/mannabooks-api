from rest_framework import serializers

from .models import LoyaltyTier


class LoyaltyTierSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = LoyaltyTier
        fields = ["id", "name", "min_points", "multiplier", "perks", "member_count", "created_at"]
        read_only_fields = ["id", "member_count", "created_at"]

    def validate_multiplier(self, value):
        if not 1 <= value <= 10:
            raise serializers.ValidationError("Use between 1 and 10.")
        return value
