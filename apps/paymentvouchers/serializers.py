from rest_framework import serializers

from apps.bills.models import Bill
from apps.core.fields import WorkspaceRelatedField
from apps.ledgeraccounts.models import LedgerAccount
from apps.suppliers.models import Supplier

from .models import PaymentVoucher


class VoucherLineSerializer(serializers.Serializer):
    bill_id = WorkspaceRelatedField(Bill, source="bill")
    bill_number = serializers.CharField(source="bill.supplier_invoice_number", read_only=True)
    bill_date = serializers.DateField(source="bill.bill_date", read_only=True)
    bill_balance = serializers.DecimalField(source="bill.balance_due", max_digits=18, decimal_places=2, read_only=True)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class PaymentVoucherSerializer(serializers.ModelSerializer):
    supplier_id = WorkspaceRelatedField(Supplier, source="supplier")
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    supplier_bank_details = serializers.CharField(source="supplier.bank_details", read_only=True)
    prepared_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    approved_by_name = serializers.CharField(source="approved_by.full_name", read_only=True, default=None)
    payment_id = serializers.UUIDField(source="payment.id", read_only=True, default=None)
    payment_number = serializers.CharField(source="payment.number", read_only=True, default=None)
    net_payable = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    withholding_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True,
                                                  help_text="Blank: the supplier's withholding rate on the amount before VAT")
    lines = VoucherLineSerializer(many=True)

    class Meta:
        model = PaymentVoucher
        fields = ["id", "number", "supplier_id", "supplier_name", "supplier_bank_details", "voucher_date", "status", "total", "withholding_amount",
                  "net_payable", "notes", "prepared_by_name", "approved_by_name", "approved_at", "payment_id", "payment_number", "lines", "created_at"]
        read_only_fields = ["id", "number", "supplier_name", "supplier_bank_details", "status", "total", "net_payable", "prepared_by_name",
                            "approved_by_name", "approved_at", "payment_id", "payment_number", "created_at"]
        extra_kwargs = {"voucher_date": {"required": False}}


class VoucherActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "pay", "cancel"])
    payment_date = serializers.DateField(required=False)
    method = serializers.ChoiceField(choices=["bank", "mpesa", "cheque", "cash"], required=False)
    paid_from_id = WorkspaceRelatedField(LedgerAccount, source="paid_from", required=False)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True)
