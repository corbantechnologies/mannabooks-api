from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.intercompanytransactions.models import IntercompanyTransaction

from .models import CompanyGroup


class GroupCompanySerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    kra_pin = serializers.CharField(allow_blank=True)
    currency = serializers.CharField()


class CompanyGroupSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    is_owner = serializers.SerializerMethodField()
    companies = serializers.SerializerMethodField()

    class Meta:
        model = CompanyGroup
        fields = ["id", "name", "currency", "notes", "owner_name", "is_owner", "companies", "created_at"]
        read_only_fields = ["id", "owner_name", "is_owner", "companies", "created_at"]

    def get_is_owner(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and obj.owner_id == request.user.pk)

    @staticmethod
    @extend_schema_field(GroupCompanySerializer(many=True))
    def get_companies(obj):
        return GroupCompanySerializer(obj.workspaces.filter(is_active=True).order_by("name"), many=True).data

    def validate_currency(self, value):
        value = value.strip().upper()
        if self.instance and value != self.instance.currency and self.instance.workspaces.exists():
            raise serializers.ValidationError("Remove the companies first to change the group's currency.")
        return value


class AddCompanySerializer(serializers.Serializer):
    workspace = serializers.SlugField(help_text="The workspace's slug")


class IntercompanySerializer(serializers.ModelSerializer):
    from_company = serializers.CharField(source="from_workspace.name", read_only=True)
    to_company = serializers.CharField(source="to_workspace.name", read_only=True)
    from_account_name = serializers.CharField(source="from_account.name", read_only=True)
    to_account_name = serializers.CharField(source="to_account.name", read_only=True)
    from_workspace = serializers.SlugField(write_only=True, help_text="Sale: the seller. Loan: the lender. Settlement: the one paying")
    to_workspace = serializers.SlugField(write_only=True)
    from_account_id = serializers.UUIDField(write_only=True)
    to_account_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = IntercompanyTransaction
        fields = ["id", "number", "kind", "from_workspace", "to_workspace", "from_company", "to_company", "transaction_date", "description",
                  "amount", "from_account_id", "to_account_id", "from_account_name", "to_account_name", "status", "void_reason", "created_at"]
        read_only_fields = ["id", "number", "from_company", "to_company", "from_account_name", "to_account_name", "status", "void_reason", "created_at"]


class IntercompanyVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class BalanceSerializer(serializers.Serializer):
    owes = serializers.CharField()
    to = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


M = {"max_digits": 18, "decimal_places": 2}


class ConsolidatedRowSerializer(serializers.Serializer):
    code = serializers.CharField(allow_blank=True)
    name = serializers.CharField()
    amounts = serializers.ListField(child=serializers.DecimalField(**M), help_text="One per company, in the order of `companies`")
    eliminations = serializers.DecimalField(**M)
    total = serializers.DecimalField(**M, help_text="The group's figure: the companies' amounts less eliminations")


class ConsolidatedSectionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    rows = ConsolidatedRowSerializer(many=True)
    amounts = serializers.ListField(child=serializers.DecimalField(**M))
    eliminations = serializers.DecimalField(**M)
    total = serializers.DecimalField(**M)


class CompanyRefSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()


class ConsolidatedPLSerializer(serializers.Serializer):
    group = serializers.CharField()
    currency = serializers.CharField()
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    companies = CompanyRefSerializer(many=True)
    sections = ConsolidatedSectionSerializer(many=True)
    gross_profit = serializers.DecimalField(**M)
    operating_profit = serializers.DecimalField(**M)
    net_profit = serializers.DecimalField(**M)
    company_net_profit = serializers.ListField(child=serializers.DecimalField(**M))
    eliminated_income = serializers.DecimalField(**M)


class ConsolidatedBSSerializer(serializers.Serializer):
    group = serializers.CharField()
    currency = serializers.CharField()
    as_of = serializers.DateField()
    companies = CompanyRefSerializer(many=True)
    groups = ConsolidatedSectionSerializer(many=True)
    total_assets = serializers.DecimalField(**M)
    total_liabilities = serializers.DecimalField(**M)
    total_equity = serializers.DecimalField(**M)
    intercompany_difference = serializers.DecimalField(**M, help_text="Owed to companies less owed by companies; should be zero")
    balanced = serializers.BooleanField()
