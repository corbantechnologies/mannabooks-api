from django.db import models

from apps.core.documents import PurchaseLine
from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class Expense(WorkspaceModel):
    """Money spent straight from a bank, M-Pesa or cash account, without a supplier bill: fuel, airtime, bank charges, petty cash."""

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"

    number = models.CharField(max_length=30)
    expense_date = models.DateField()
    paid_from = models.ForeignKey("bankaccounts.BankAccount", on_delete=models.PROTECT, related_name="expenses")
    payee = models.CharField(max_length=150, blank=True)
    supplier = models.ForeignKey("suppliers.Supplier", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses")
    method = models.CharField(max_length=10, choices=[("cash", "Cash"), ("mpesa", "M-Pesa"), ("bank", "Bank transfer"), ("card", "Card"),
                                                      ("cheque", "Cheque")], default="cash")
    reference = models.CharField(max_length=60, blank=True)
    supplier_etims_number = models.CharField(max_length=80, blank=True, help_text="eTIMS CU number on the receipt, to claim its VAT")
    prices_include_tax = models.BooleanField(default=True)
    subtotal = models.DecimalField(**MONEY_FIELD, default=0)
    tax_total = models.DecimalField(**MONEY_FIELD, default=0)
    total = models.DecimalField(**MONEY_FIELD, default=0)
    notes = models.TextField(blank=True)
    cost_center = models.ForeignKey("costcenters.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return self.number


class ExpenseLine(PurchaseLine):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="lines")
