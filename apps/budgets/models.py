from django.conf import settings
from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class Budget(WorkspaceModel):
    """
    Planned income and spending for one financial year, month by month: for the whole business, or for
    one cost centre or project. Once approved, it is compared with the ledger and warns about overspending.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"

    name = models.CharField(max_length=120)
    fiscal_year = models.ForeignKey("fiscalyears.FiscalYear", on_delete=models.PROTECT, related_name="budgets")
    cost_center = models.ForeignKey("costcenters.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fiscal_year__start_date", "name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "fiscal_year", "name"], name="unique_budget_name_per_year")]

    def __str__(self):
        return f"{self.name} ({self.fiscal_year})"


class BudgetLine(BaseModel):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    amounts = models.JSONField(default=list, help_text="12 monthly amounts, from the year's first month, as strings")
    total = models.DecimalField(**MONEY_FIELD, default=0)

    class Meta:
        ordering = ["account__code"]
        constraints = [models.UniqueConstraint(fields=["budget", "account"], name="one_budget_line_per_account")]
