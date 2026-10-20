from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.core.money import MONEY_FIELD


class IntercompanyTransaction(BaseModel):
    """
    Money or goods moving between two companies of a group, recorded once and posted in both sets of books:

    - sale: `from` sells to `to` (income for one, a cost for the other), on account;
    - loan: `from` lends money to `to`;
    - settlement: `from` pays `to` what it owes.

    Both sides go through "Due from group companies" and "Due to group companies", which cancel out when the group is consolidated.
    """

    class Kind(models.TextChoices):
        SALE = "sale", "Sale or recharge"
        LOAN = "loan", "Loan"
        SETTLEMENT = "settlement", "Settlement (paying what is owed)"

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"

    group = models.ForeignKey("companygroups.CompanyGroup", on_delete=models.CASCADE, related_name="transactions")
    number = models.CharField(max_length=20)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    from_workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="+")
    to_workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT, related_name="+")
    transaction_date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(**MONEY_FIELD)
    from_account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+",
                                     help_text="Sale: the seller's income account. Loan or settlement: the bank or cash account the money leaves")
    to_account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+",
                                   help_text="Sale: the buyer's expense or asset account. Loan or settlement: the bank or cash account the money reaches")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)
    void_reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-transaction_date", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["group", "number"], name="unique_intercompany_number")]

    def __str__(self):
        return f"{self.number}: {self.description}"
