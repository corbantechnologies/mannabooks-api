from django.db import models

from apps.core.models import WorkspaceModel

DEFAULT_MESSAGE = (
    "Dear {customer},\n\nThis is a reminder that invoice {number} for {currency} {balance} is due on {due_date}.\n\n"
    "If you have already paid, thank you, and please ignore this message.\n\nRegards,\n{business}"
)


class ReminderRule(WorkspaceModel):
    """When to email customers about an unpaid invoice: days before (negative) or after (positive) the due date."""

    name = models.CharField(max_length=80)
    days = models.SmallIntegerField(help_text="-3: three days before the due date, 0: on it, 7: a week after")
    subject = models.CharField(max_length=200, default="Payment reminder: invoice {number}")
    message = models.TextField(default=DEFAULT_MESSAGE)
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["days"]

    def __str__(self):
        return self.name


class ReminderLog(WorkspaceModel):
    """A reminder email that was sent (automatically by a rule, or by hand from an invoice)."""

    rule = models.ForeignKey(ReminderRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs")
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.CASCADE, related_name="reminders")
    sent_to = models.EmailField()
    subject = models.CharField(max_length=200)
    error = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["rule", "invoice"], condition=models.Q(rule__isnull=False), name="one_reminder_per_rule")]
