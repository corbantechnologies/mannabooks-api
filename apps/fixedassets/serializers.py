from rest_framework import serializers

from apps.bankaccounts.models import BankAccount
from apps.bills.models import Bill
from apps.branches.models import Branch
from apps.core.fields import WorkspaceRelatedField
from apps.costcenters.models import CostCenter
from apps.employees.models import Employee
from apps.ledgeraccounts.models import LedgerAccount
from apps.suppliers.models import Supplier

from .models import FixedAsset

M = {"max_digits": 18, "decimal_places": 2}


class FixedAssetSerializer(serializers.ModelSerializer):
    location_id = WorkspaceRelatedField(Branch, source="location", allow_null=True, required=False)
    location_name = serializers.CharField(source="location.name", read_only=True, default=None)
    custodian_id = WorkspaceRelatedField(Employee, source="custodian", allow_null=True, required=False)
    custodian_name = serializers.CharField(source="custodian.full_name", read_only=True, default=None)
    cost_center_id = WorkspaceRelatedField(CostCenter, source="cost_center", allow_null=True, required=False)
    cost_center_name = serializers.CharField(source="cost_center.name", read_only=True, default=None)
    supplier_id = WorkspaceRelatedField(Supplier, source="supplier", allow_null=True, required=False)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default=None)
    bill_id = WorkspaceRelatedField(Bill, source="bill", allow_null=True, required=False)
    bill_number = serializers.CharField(source="bill.supplier_invoice_number", read_only=True, default=None)
    asset_account_id = WorkspaceRelatedField(LedgerAccount, source="asset_account", required=False)
    asset_account_name = serializers.CharField(source="asset_account.name", read_only=True)
    accumulated_account_id = WorkspaceRelatedField(LedgerAccount, source="accumulated_account", required=False)
    expense_account_id = WorkspaceRelatedField(LedgerAccount, source="expense_account", required=False)
    expense_account_name = serializers.CharField(source="expense_account.name", read_only=True)
    disposal_account_name = serializers.CharField(source="disposal_account.name", read_only=True, default=None)
    book_value = serializers.DecimalField(**M, read_only=True)

    class Meta:
        model = FixedAsset
        fields = ["id", "number", "name", "description", "category", "serial_number", "location_id", "location_name", "custodian_id", "custodian_name",
                  "cost_center_id", "cost_center_name", "supplier_id", "supplier_name", "bill_id", "bill_number", "asset_account_id", "asset_account_name",
                  "accumulated_account_id", "expense_account_id", "expense_account_name", "acquisition", "purchase_date", "in_service_date", "cost",
                  "residual_value", "method", "useful_life_months", "rate_percent", "opening_accumulated", "accumulated_depreciation", "book_value",
                  "depreciated_to", "status", "disposal_date", "disposal_proceeds", "disposal_account_name", "disposal_gain", "notes", "created_at"]
        read_only_fields = ["id", "number", "location_name", "custodian_name", "cost_center_name", "supplier_name", "bill_number", "asset_account_name",
                            "expense_account_name", "accumulated_depreciation", "book_value", "status", "disposal_date", "disposal_proceeds",
                            "disposal_account_name", "disposal_gain", "created_at"]
        extra_kwargs = {"in_service_date": {"required": False}, "method": {"required": False}, "useful_life_months": {"required": False},
                        "rate_percent": {"required": False}}


class AssetActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["dispose", "undo_disposal"])
    date = serializers.DateField(required=False)
    proceeds = serializers.DecimalField(**M, required=False, default=0, min_value=0)
    received_into_id = WorkspaceRelatedField(BankAccount, source="received_into", allow_null=True, required=False)


class ScheduleRowSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    opening = serializers.DecimalField(**M)
    depreciation = serializers.DecimalField(**M)
    closing = serializers.DecimalField(**M)


class DepreciationHistorySerializer(serializers.Serializer):
    month_end = serializers.DateField()
    amount = serializers.DecimalField(**M)


class AssetScheduleSerializer(serializers.Serializer):
    history = DepreciationHistorySerializer(many=True)
    projection = ScheduleRowSerializer(many=True)


class CategoryDefaultSerializer(serializers.Serializer):
    category = serializers.CharField()
    label = serializers.CharField()
    method = serializers.CharField()
    useful_life_months = serializers.IntegerField()
    rate_percent = serializers.DecimalField(max_digits=6, decimal_places=2)
    asset_account_id = serializers.UUIDField(allow_null=True)
