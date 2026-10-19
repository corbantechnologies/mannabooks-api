from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class OtherIncome(WorkspaceModel):
    """Money received that isn't a sale to a customer: interest, rent received, commission, grants, refunds."""

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"

    number = models.CharField(max_length=30)
    income_date = models.DateField()
    received_into = models.ForeignKey("bankaccounts.BankAccount", on_delete=models.PROTECT, related_name="other_incomes")
    payer = models.CharField(max_length=150, blank=True)
    reference = models.CharField(max_length=60, blank=True)
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
        ordering = ["-income_date", "-created_at"]

    def __str__(self):
        return self.number


class OtherIncomeLine(BaseModel):
    income = models.ForeignKey(OtherIncome, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=255)
    account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    tax_rate = models.ForeignKey("taxrates.TaxRate", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(**MONEY_FIELD)
    net_amount = models.DecimalField(**MONEY_FIELD, default=0)
    tax_amount = models.DecimalField(**MONEY_FIELD, default=0)
    total_amount = models.DecimalField(**MONEY_FIELD, default=0)
