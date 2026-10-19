from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class OpeningBalance(WorkspaceModel):
    """
    The balances the business starts MannaBooks with, dated the day before its first day on MannaBooks.
    Posting creates one journal entry; any difference goes to Opening balance equity.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"

    as_of_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    journal = models.OneToOneField("journals.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_opening_balance_per_workspace")]

    def __str__(self):
        return f"Opening balances at {self.as_of_date}"


class OpeningBalanceLine(BaseModel):
    opening_balance = models.ForeignKey(OpeningBalance, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    debit = models.DecimalField(**MONEY_FIELD, default=0)
    credit = models.DecimalField(**MONEY_FIELD, default=0)

    class Meta:
        ordering = ["account__code"]
        constraints = [models.UniqueConstraint(fields=["opening_balance", "account"], name="one_opening_line_per_account")]
