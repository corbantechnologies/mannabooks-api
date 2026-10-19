from rest_framework import serializers

from .models import Currency


class CurrencySerializer(serializers.ModelSerializer):
    latest_rate = serializers.SerializerMethodField()

    class Meta:
        model = Currency
        fields = ["id", "code", "name", "symbol", "decimal_places", "is_base", "is_active", "latest_rate"]
        read_only_fields = ["id", "is_base", "latest_rate"]

    def get_latest_rate(self, obj) -> str | None:
        if obj.is_base:
            return "1"
        rate = obj.rates.order_by("-rate_date").values_list("rate", flat=True).first()
        return str(rate) if rate is not None else None

    def validate_code(self, value):
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use the 3-letter ISO code, for example USD.")
        clash = Currency.objects.filter(workspace=self.context["workspace"], code=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("This currency is already set up.")
        return value

    def validate(self, attrs):
        if self.instance and self.instance.is_base:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": ["The base currency can't be deactivated."]})
            if "code" in attrs and attrs["code"] != self.instance.code:
                raise serializers.ValidationError({"code": ["The base currency can't be changed."]})
        return attrs
