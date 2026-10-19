from rest_framework import serializers

from apps.currencies.models import Currency

from .models import ExchangeRate


class ExchangeRateSerializer(serializers.ModelSerializer):
    currency_id = serializers.PrimaryKeyRelatedField(source="currency", queryset=Currency.objects.none())
    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = ExchangeRate
        fields = ["id", "currency_id", "currency_code", "rate_date", "rate", "source", "created_at"]
        read_only_fields = ["id", "currency_code", "source", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workspace = self.context.get("workspace")
        if workspace is not None:
            self.fields["currency_id"].queryset = Currency.objects.filter(workspace=workspace)

    def validate_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError("The rate must be more than zero.")
        return value

    def validate(self, attrs):
        currency = attrs.get("currency", getattr(self.instance, "currency", None))
        if currency and currency.is_base:
            raise serializers.ValidationError({"currency_id": ["The base currency's rate is always 1."]})
        rate_date = attrs.get("rate_date", getattr(self.instance, "rate_date", None))
        clash = ExchangeRate.objects.filter(workspace=self.context["workspace"], currency=currency, rate_date=rate_date)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError({"rate_date": ["There is already a rate for this currency on this date. Edit it instead."]})
        return attrs
