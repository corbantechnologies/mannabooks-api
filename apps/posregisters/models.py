from django.db import models

from apps.core.models import WorkspaceModel


class PosRegister(WorkspaceModel):
    """A till: where cashiers open shifts and sell. Each payment method lands in its own account."""

    name = models.CharField(max_length=80)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cash_account = models.ForeignKey("ledgeraccounts.LedgerAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                     help_text="Blank: Cash on hand")
    mpesa_account = models.ForeignKey("ledgeraccounts.LedgerAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                      help_text="Blank: M-Pesa")
    card_account = models.ForeignKey("ledgeraccounts.LedgerAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                     help_text="Blank: Bank account")
    receipt_footer = models.CharField(max_length=255, blank=True, default="Thank you for shopping with us.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_register_name")]

    def __str__(self):
        return self.name

    def account_for(self, method: str):
        from apps.ledgeraccounts.services import system_account

        own = {"cash": self.cash_account, "mpesa": self.mpesa_account, "card": self.card_account, "bank": self.card_account}.get(method)
        return own or system_account(self.workspace, {"cash": "cash", "mpesa": "mpesa"}.get(method, "bank"))
