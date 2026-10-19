from django.db import models

from apps.core.models import WorkspaceModel


class BankAccount(WorkspaceModel):
    """
    A bank account, M-Pesa till or paybill, or cash box, with its ledger account. Its balance is the ledger
    account's balance; its statement lines and reconciliations hang off it.
    """

    class Kind(models.TextChoices):
        BANK = "bank", "Bank account"
        MOBILE = "mobile", "M-Pesa / mobile money"
        CASH = "cash", "Cash"

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.BANK)
    ledger_account = models.OneToOneField("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="bank_account")
    bank_name = models.CharField(max_length=100, blank=True)
    branch = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=40, blank=True, help_text="Or the till / paybill number")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
