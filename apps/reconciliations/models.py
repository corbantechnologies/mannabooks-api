from django.conf import settings
from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class Reconciliation(WorkspaceModel):
    """
    Proof that the books agree with a bank statement on a date: the transactions ticked as cleared, plus the
    last reconciled balance, must equal the statement's closing balance.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    bank_account = models.ForeignKey("bankaccounts.BankAccount", on_delete=models.PROTECT, related_name="reconciliations")
    statement_date = models.DateField()
    statement_balance = models.DecimalField(**MONEY_FIELD, help_text="Closing balance on the bank statement")
    opening_balance = models.DecimalField(**MONEY_FIELD, default=0, help_text="The previous reconciliation's statement balance")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-statement_date"]

    def __str__(self):
        return f"{self.bank_account} at {self.statement_date}"


class ReconciledLine(BaseModel):
    """A transaction ticked as cleared on the statement. Protected: a reconciled transaction can't be removed."""

    reconciliation = models.ForeignKey(Reconciliation, on_delete=models.CASCADE, related_name="lines")
    journal_line = models.OneToOneField("journals.JournalLine", on_delete=models.PROTECT, related_name="reconciled")
