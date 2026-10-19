from rest_framework import serializers

from apps.branches.models import Branch
from apps.core.dimensions import DimensionFields
from apps.core.fields import WorkspaceRelatedField
from apps.core.kra import clean_pin
from apps.core.sales_serializers import ETIMS_FIELDS, SALES_DOCUMENT_FIELDS, SALES_READ_ONLY, SalesLineSerializer
from apps.customers.models import Customer
from apps.ledgeraccounts.models import LedgerAccount
from apps.posshifts.models import PosShift

from .models import Receipt


class ReceiptSerializer(DimensionFields, serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer", allow_null=True, required=False)
    customer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    deposit_account_id = WorkspaceRelatedField(LedgerAccount, source="deposit_account", required=False)
    shift_id = WorkspaceRelatedField(PosShift, source="shift", allow_null=True, required=False)
    mpesa_transaction_id = serializers.UUIDField(write_only=True, required=False, allow_null=True,
                                                 help_text="A completed M-Pesa prompt that paid for this sale")
    redeem_points = serializers.IntegerField(write_only=True, required=False, min_value=0, default=0,
                                             help_text="Loyalty points the customer spends on this sale")
    deposit_account_name = serializers.CharField(source="deposit_account.name", read_only=True)
    branch_id = WorkspaceRelatedField(Branch, source="branch", allow_null=True, required=False)
    lines = SalesLineSerializer(many=True)

    class Meta:
        model = Receipt
        fields = SALES_DOCUMENT_FIELDS + ETIMS_FIELDS + [
            "customer_pin", "method", "payment_reference", "deposit_account_id", "deposit_account_name", "status",
            "void_reason", "branch_id", "shift_id", "mpesa_transaction_id", "redeem_points",
        ]
        read_only_fields = [f for f in SALES_READ_ONLY if f != "customer_name"] + ETIMS_FIELDS + ["deposit_account_name", "status", "void_reason"]
        extra_kwargs = {"currency": {"required": False}}

    def validate_customer_pin(self, value):
        return clean_pin(value)


class ReceiptVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
