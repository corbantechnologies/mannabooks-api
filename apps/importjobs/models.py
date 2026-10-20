from django.db import models

from apps.core.models import WorkspaceModel


class ImportJob(WorkspaceModel):
    """
    A spreadsheet (CSV) brought into the workspace: customers, suppliers, products or opening balances.
    It is checked row by row first; it imports only when every row is right, so nothing is half done.
    """

    class Kind(models.TextChoices):
        CUSTOMERS = "customers", "Customers"
        SUPPLIERS = "suppliers", "Suppliers"
        PRODUCTS = "products", "Products and services"
        OPENING_BALANCES = "opening_balances", "Opening balances"

    class Status(models.TextChoices):
        CHECKED = "checked", "Checked, not imported"
        IMPORTED = "imported", "Imported"
        FAILED = "failed", "Has errors"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices)
    total_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0, help_text="Already there (same name or code), left as they were")
    errors = models.JSONField(default=list, help_text="[{row, message}]")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} from {self.filename}"
