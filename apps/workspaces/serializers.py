from rest_framework import serializers

from .models import Workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = [
            "id", "name", "slug", "legal_name", "kra_pin", "vat_registered", "vat_number", "currency",
            "country", "timezone", "phone", "email", "address", "logo_url", "fiscal_year_start_month",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at"]

    def validate_kra_pin(self, value):
        value = value.strip().upper()
        if value and (len(value) != 11 or not value[0].isalpha() or not value[-1].isalpha() or not value[1:-1].isdigit()):
            raise serializers.ValidationError("A KRA PIN looks like A123456789B.")
        return value

    def validate_currency(self, value):
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use a 3-letter currency code, for example KES.")
        return value

    def validate(self, attrs):
        vat_registered = attrs.get("vat_registered", getattr(self.instance, "vat_registered", False))
        kra_pin = attrs.get("kra_pin", getattr(self.instance, "kra_pin", ""))
        if vat_registered and not kra_pin:
            raise serializers.ValidationError({"kra_pin": ["A VAT-registered business needs its KRA PIN."]})
        return attrs


class MyWorkspaceSerializer(WorkspaceSerializer):
    """A workspace in the caller's list, with their role in it."""

    role = serializers.SerializerMethodField()

    class Meta(WorkspaceSerializer.Meta):
        fields = WorkspaceSerializer.Meta.fields + ["role"]

    def get_role(self, obj) -> str | None:
        user = self.context["request"].user
        membership = next((m for m in obj.memberships.all() if m.user_id == user.id), None)
        return membership.role.name if membership else None


class WorkspaceContextSerializer(serializers.Serializer):
    """Everything the web app needs about the caller inside one workspace."""

    workspace = WorkspaceSerializer()
    membership_id = serializers.UUIDField()
    role = serializers.CharField()
    role_slug = serializers.CharField()
    permissions = serializers.ListField(child=serializers.CharField())
    is_owner = serializers.BooleanField()
    employee_id = serializers.UUIDField(allow_null=True)
    department = serializers.CharField(allow_null=True)
    in_charge_of = serializers.ListField(child=serializers.CharField())
    etims_enabled = serializers.BooleanField(help_text="KRA eTIMS signing is switched on for the platform")
