from django.conf import settings
from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD


class JournalEntry(WorkspaceModel):
    """
    A balanced set of debits and credits. Manual entries start as drafts; posting checks the balance and
    the period, then numbers them. Entries from other modules (invoices, payroll...) are posted directly
    and carry their source, so the source can replace them when it changes.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    number = models.CharField(max_length=30, blank=True)
    entry_date = models.DateField()
    description = models.CharField(max_length=255)
    reference = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    source = models.CharField(max_length=30, default="manual", help_text="manual, opening_balance, year_end, invoice, ...")
    source_model = models.CharField(max_length=80, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    period = models.ForeignKey("periods.AccountingPeriod", null=True, blank=True, on_delete=models.PROTECT, related_name="entries")
    reversal_of = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name_plural = "journal entries"
        indexes = [
            models.Index(fields=["workspace", "entry_date"]),
            models.Index(fields=["workspace", "source_model", "source_id"]),
        ]

    def __str__(self):
        return self.number or f"Draft {self.entry_date}"


class JournalLine(BaseModel):
    """One debit or credit in an entry, in the base currency."""

    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="lines")
    description = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(**MONEY_FIELD, default=0)
    credit = models.DecimalField(**MONEY_FIELD, default=0)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    department = models.ForeignKey("departments.Department", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cost_center = models.ForeignKey("costcenters.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    line_no = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["line_no"]
        constraints = [
            models.CheckConstraint(condition=models.Q(debit__gte=0) & models.Q(credit__gte=0), name="journal_line_not_negative"),
            models.CheckConstraint(
                condition=(models.Q(debit=0) & models.Q(credit__gt=0)) | (models.Q(credit=0) & models.Q(debit__gt=0)),
                name="journal_line_one_side",
            ),
        ]

    def __str__(self):
        return f"{self.account} Dr {self.debit} Cr {self.credit}"
