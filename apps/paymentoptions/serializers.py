from rest_framework import serializers

from .models import PaymentOption


class PaymentOptionSerializer(serializers.ModelSerializer):
    lines = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = PaymentOption
        fields = ["id", "kind", "bank_name", "branch", "account_name", "account_number", "swift_code", "number", "instructions",
                  "show_on_documents", "sort_order", "lines", "created_at"]
        read_only_fields = ["id", "lines", "created_at"]

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        get = lambda f: attrs.get(f, getattr(self.instance, f, "")) if self.instance else attrs.get(f, "")  # noqa: E731
        if kind == PaymentOption.Kind.BANK and not (get("bank_name") and get("account_number")):
            raise serializers.ValidationError({"account_number": ["Enter the bank and the account number."]})
        if kind in (PaymentOption.Kind.PAYBILL, PaymentOption.Kind.TILL, PaymentOption.Kind.POCHI) and not get("number"):
            raise serializers.ValidationError({"number": ["Enter the number customers pay to."]})
        if kind == PaymentOption.Kind.OTHER and not get("instructions"):
            raise serializers.ValidationError({"instructions": ["Say how customers should pay."]})
        return attrs
