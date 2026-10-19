from django.utils import timezone
from rest_framework import serializers

from apps.branches.models import Branch
from apps.core.dimensions import DimensionFields
from apps.core.fields import WorkspaceRelatedField
from apps.core.sales_serializers import ETIMS_FIELDS, SALES_DOCUMENT_FIELDS, SALES_READ_ONLY, SalesLineSerializer
from apps.customers.models import Customer

from .models import Invoice


class InvoiceSerializer(DimensionFields, serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer")
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    branch_id = WorkspaceRelatedField(Branch, source="branch", allow_null=True, required=False)
    lines = SalesLineSerializer(many=True, required=False)
    original_invoice_id = WorkspaceRelatedField(Invoice, source="original_invoice", allow_null=True, required=False)
    original_invoice_number = serializers.CharField(source="original_invoice.number", read_only=True, default=None)
    is_overdue = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = SALES_DOCUMENT_FIELDS + ETIMS_FIELDS + [
            "kind", "original_invoice_id", "original_invoice_number", "status", "due_date", "amount_paid", "balance_due", "is_overdue", "branch_id", "quotation", "void_reason",
            "issued_at", "payments",
        ]
        read_only_fields = SALES_READ_ONLY + ETIMS_FIELDS + [
            "original_invoice_number", "status", "amount_paid", "balance_due", "is_overdue", "quotation", "void_reason", "issued_at", "payments",
        ]
        extra_kwargs = {"kind": {"required": False}, "currency": {"required": False}, "issue_date": {"required": False}, "due_date": {"required": False}}

    def get_is_overdue(self, obj) -> bool:
        return obj.status in ("issued", "partially_paid") and obj.due_date < timezone.localdate()

    def get_payments(self, obj) -> list[dict]:
        """Payments and credit notes applied to this invoice."""
        if self.context.get("list"):
            return []
        rows = [
            {"kind": "payment", "id": str(a.payment_id), "number": a.payment.number, "date": a.payment.payment_date, "amount": str(a.amount)}
            for a in obj.allocations.filter(payment__status="posted").select_related("payment")
        ]
        rows += [
            {"kind": "credit_note", "id": str(c.id), "number": c.number, "date": c.issue_date, "amount": str(c.applied_amount)}
            for c in obj.credit_notes.filter(status="issued")
        ]
        return sorted(rows, key=lambda r: r["date"])


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
