from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class Payment(WorkspaceModel):
    """Money received from a customer, applied to one or more of their invoices."""

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        MPESA = "mpesa", "M-Pesa"
        BANK = "bank", "Bank transfer"
        CHEQUE = "cheque", "Cheque"
        CARD = "card", "Card"

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"

    number = models.CharField(max_length=30)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField()
    amount = models.DecimalField(**MONEY_FIELD)
    method = models.CharField(max_length=10, choices=Method.choices)
    reference = models.CharField(max_length=60, blank=True, help_text="M-Pesa code, cheque or bank reference")
    deposit_account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    unallocated_amount = models.DecimalField(**MONEY_FIELD, default=0)
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return self.number


class PaymentAllocation(BaseModel):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="allocations")
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(**MONEY_FIELD)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["payment", "invoice"], name="one_allocation_per_invoice")]
