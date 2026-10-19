from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class BankTransfer(WorkspaceModel):
    """Money moved between the business's own accounts: banking cash, M-Pesa to bank, topping up petty cash."""

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"

    number = models.CharField(max_length=30)
    transfer_date = models.DateField()
    from_account = models.ForeignKey("bankaccounts.BankAccount", on_delete=models.PROTECT, related_name="+")
    to_account = models.ForeignKey("bankaccounts.BankAccount", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(**MONEY_FIELD)
    fee = models.DecimalField(**MONEY_FIELD, default=0, help_text="Bank or M-Pesa charge, taken from the sending account")
    reference = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.POSTED)

    class Meta:
        ordering = ["-transfer_date", "-created_at"]

    def __str__(self):
        return self.number
