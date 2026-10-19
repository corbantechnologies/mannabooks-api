from django.conf import settings
from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class PosShift(WorkspaceModel):
    """A cashier's session at a till, from opening float to cash count. Sales in it are cash sales linked to it."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    number = models.CharField(max_length=30)
    register = models.ForeignKey("posregisters.PosRegister", on_delete=models.PROTECT, related_name="shifts")
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_float = models.DecimalField(**MONEY_FIELD, default=0)
    expected_cash = models.DecimalField(**MONEY_FIELD, default=0)
    counted_cash = models.DecimalField(**MONEY_FIELD, null=True, blank=True)
    cash_difference = models.DecimalField(**MONEY_FIELD, default=0, help_text="Counted less expected: negative is short")
    closing_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["register"], condition=models.Q(status="open"), name="one_open_shift_per_register"),
            models.UniqueConstraint(fields=["workspace", "cashier"], condition=models.Q(status="open"), name="one_open_shift_per_cashier"),
        ]

    def __str__(self):
        return self.number
