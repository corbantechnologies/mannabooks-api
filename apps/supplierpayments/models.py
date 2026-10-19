from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class SupplierPayment(WorkspaceModel):
    """
    Money paid to a supplier, applied to their bills. Withholding tax kept back is owed to KRA, and still
    settles the bill: the bill is cleared by amount + withholding.
    """

    class Method(models.TextChoices):
        BANK = "bank", "Bank transfer"
        MPESA = "mpesa", "M-Pesa"
        CHEQUE = "cheque", "Cheque"
        CASH = "cash", "Cash"

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"

    number = models.CharField(max_length=30)
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT, related_name="payments")
    payment_date = models.DateField()
    amount = models.DecimalField(**MONEY_FIELD, help_text="Money that left the account")
    withholding_amount = models.DecimalField(**MONEY_FIELD, default=0, help_text="Withholding tax kept back for KRA")
    method = models.CharField(max_length=10, choices=Method.choices)
    reference = models.CharField(max_length=60, blank=True, help_text="Cheque number, bank or M-Pesa reference")
    paid_from = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    unallocated_amount = models.DecimalField(**MONEY_FIELD, default=0)
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return self.number


class SupplierPaymentAllocation(BaseModel):
    payment = models.ForeignKey(SupplierPayment, on_delete=models.CASCADE, related_name="allocations")
    bill = models.ForeignKey("bills.Bill", on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(**MONEY_FIELD)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["payment", "bill"], name="one_allocation_per_bill")]
