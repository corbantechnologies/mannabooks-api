from rest_framework import serializers

from apps.core.kra import clean_pin

from .models import Workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    group_id = serializers.UUIDField(read_only=True, allow_null=True)
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)

    class Meta:
        model = Workspace
        fields = [
            "id", "name", "slug", "legal_name", "kra_pin", "vat_registered", "vat_number", "currency",
            "country", "timezone", "phone", "email", "address", "logo_url", "fiscal_year_start_month",
            "modules", "business_goal", "group_id", "group_name", "created_at",
        ]
        read_only_fields = ["id", "slug", "group_id", "group_name", "created_at"]

    def validate_kra_pin(self, value):
        return clean_pin(value)

    def validate_modules(self, value):
        from apps.core.catalog import APP_MODULES

        if not isinstance(value, list) or any(m not in APP_MODULES for m in value):
            raise serializers.ValidationError(f"Use these module names: {', '.join(APP_MODULES)}.")
        return [m for m in APP_MODULES if m in value]  # keep the catalogue's order, no repeats

    def validate_business_goal(self, value):
        from apps.core.catalog import GOALS

        if value and value not in GOALS:
            raise serializers.ValidationError(f"Use one of: {', '.join(GOALS)}.")
        return value

    def validate_fiscal_year_start_month(self, value):
        if self.instance is not None and value != self.instance.fiscal_year_start_month:
            from apps.journals.models import JournalEntry

            if JournalEntry.objects.filter(workspace=self.instance).exists():
                raise serializers.ValidationError("This can't change once transactions are posted: the financial years are already in use.")
        return value

    def update(self, instance, validated_data):
        month_changed = "fiscal_year_start_month" in validated_data and validated_data["fiscal_year_start_month"] != instance.fiscal_year_start_month
        instance = super().update(instance, validated_data)
        if month_changed:
            from apps.fiscalyears.services import restart_years

            restart_years(instance)
        return instance

    def validate_currency(self, value):
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use a 3-letter currency code, for example KES.")
        return value

    def validate(self, attrs):
        from apps.core.catalog import APP_MODULES, GOALS

        goal = attrs.get("business_goal")
        if goal and "modules" not in attrs:  # choosing a goal switches on what it needs
            attrs["modules"] = [m for m in APP_MODULES if m in GOALS[goal]["modules"]]
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
    fiscal_years = serializers.ListField(child=serializers.DictField(), help_text="Every financial year, latest first: id, name, start_date, end_date, status")
    unclosed_years = serializers.ListField(child=serializers.CharField(), help_text="Years that have ended but are not closed yet")
    inbox_new = serializers.IntegerField(help_text="Documents from other businesses waiting in the inbox")
    module_catalog = serializers.ListField(child=serializers.DictField(), help_text="Modules that can be switched on: key, label, description")
    goal_catalog = serializers.ListField(child=serializers.DictField(), help_text="Starting goals: key, label, description, modules")
