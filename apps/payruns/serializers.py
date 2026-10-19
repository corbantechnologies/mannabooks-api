import calendar

from rest_framework import serializers

from apps.bankaccounts.models import BankAccount
from apps.core.fields import WorkspaceRelatedField

from .models import PayRun


class PayRunSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    approved_by_name = serializers.CharField(source="approved_by.full_name", read_only=True, default=None)
    paid_from_name = serializers.CharField(source="paid_from.name", read_only=True, default=None)
    employees = serializers.IntegerField(source="payslips.count", read_only=True)

    class Meta:
        model = PayRun
        fields = ["id", "name", "year", "month", "pay_date", "status", "employees", "gross_pay", "total_paye", "total_shif", "total_nssf",
                  "total_housing_levy", "total_other_deductions", "net_pay", "employer_cost", "approved_by_name", "approved_at", "paid_from_name",
                  "paid_at", "remittances", "created_at"]
        read_only_fields = [f for f in fields if f not in ("year", "month", "pay_date")]
        extra_kwargs = {"pay_date": {"required": False}}

    def get_name(self, obj) -> str:
        return f"{calendar.month_name[obj.month]} {obj.year}"


class PayRunActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reopen", "pay", "remit"])
    bank_account_id = WorkspaceRelatedField(BankAccount, source="bank_account", required=False)
    date = serializers.DateField(required=False)
    kind = serializers.ChoiceField(choices=["paye", "shif", "nssf", "housing_levy"], required=False)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True)
