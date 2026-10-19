from django.db import models

from apps.core.models import WorkspaceModel


class Supplier(WorkspaceModel):
    """Someone the business buys from."""

    class Kind(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        COMPANY = "company", "Company"

    number = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.COMPANY)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=80, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    withholding_tax_rate = models.ForeignKey("taxrates.TaxRate", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                             help_text="Withholding tax deducted when paying them, e.g. 5% on professional fees")
    bank_details = models.TextField(blank=True, help_text="Bank, branch and account, or paybill and account")
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "number"], name="unique_supplier_number")]

    def __str__(self):
        return self.name
