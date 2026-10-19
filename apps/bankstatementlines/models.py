from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class BankStatementLine(WorkspaceModel):
    """
    One line of a bank or M-Pesa statement (imported from CSV or typed). Matching links it to the
    transaction in the books; lines with nothing in the books can become an expense or other income.
    """

    class Status(models.TextChoices):
        UNMATCHED = "unmatched", "To match"
        MATCHED = "matched", "Matched"
        EXCLUDED = "excluded", "Ignored"

    bank_account = models.ForeignKey("bankaccounts.BankAccount", on_delete=models.CASCADE, related_name="statement_lines")
    line_date = models.DateField()
    description = models.CharField(max_length=255)
    reference = models.CharField(max_length=80, blank=True)
    amount = models.DecimalField(**MONEY_FIELD, help_text="Positive: money in. Negative: money out.")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNMATCHED)
    journal_line = models.ForeignKey("journals.JournalLine", null=True, blank=True, on_delete=models.SET_NULL, related_name="statement_lines")
    import_batch = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-line_date", "-created_at"]
        indexes = [models.Index(fields=["bank_account", "status"])]
