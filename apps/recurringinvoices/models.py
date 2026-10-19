from django.db import models

from apps.core.models import BaseModel, WorkspaceModel


class RecurringInvoice(WorkspaceModel):
    """A template that raises the same invoice on a schedule (rent, retainers, subscriptions)."""

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Every 3 months"
        YEARLY = "yearly", "Yearly"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        ENDED = "ended", "Ended"

    name = models.CharField(max_length=120)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="recurring_invoices")
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY)
    start_date = models.DateField()
    next_run_date = models.DateField()
    end_date = models.DateField(null=True, blank=True, help_text="Blank: until stopped")
    auto_issue = models.BooleanField(default=False, help_text="Issue the invoices; otherwise they wait as drafts")
    prices_include_tax = models.BooleanField(default=False)
    reference = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    invoices_created = models.PositiveIntegerField(default=0)
    last_invoice = models.ForeignKey("invoices.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    last_error = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["next_run_date", "name"]
        indexes = [models.Index(fields=["status", "next_run_date"])]

    def __str__(self):
        return self.name


class RecurringInvoiceLine(BaseModel):
    """Leave the price or VAT blank to use the product's current price and VAT when each invoice is raised."""

    recurring_invoice = models.ForeignKey(RecurringInvoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("products.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_rate = models.ForeignKey("taxrates.TaxRate", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    line_no = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["line_no"]
