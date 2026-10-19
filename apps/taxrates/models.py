from django.db import models

from apps.core.models import WorkspaceModel


class TaxRate(WorkspaceModel):
    """A tax charged on lines (VAT) or withheld from payments (withholding VAT and income tax)."""

    class Kind(models.TextChoices):
        VAT = "vat", "VAT"
        WITHHOLDING_VAT = "withholding_vat", "Withholding VAT"
        WITHHOLDING_TAX = "withholding_tax", "Withholding income tax"

    class EtimsCode(models.TextChoices):
        EXEMPT = "A", "A: Exempt"
        STANDARD = "B", "B: 16%"
        ZERO = "C", "C: 0%"
        NON_VAT = "D", "D: Non-VAT"
        EIGHT = "E", "E: 8%"

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.VAT)
    rate = models.DecimalField(max_digits=6, decimal_places=3, help_text="Percent, e.g. 16.000")
    etims_code = models.CharField("KRA eTIMS tax code", max_length=1, choices=EtimsCode.choices, blank=True)
    sales_account = models.ForeignKey(
        "ledgeraccounts.LedgerAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Where tax charged on sales is posted",
    )
    purchases_account = models.ForeignKey(
        "ledgeraccounts.LedgerAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Where tax paid on purchases is posted",
    )
    is_default = models.BooleanField(default=False, help_text="Used on new lines unless another rate is chosen")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "-rate", "code"]
        constraints = [models.UniqueConstraint(fields=["workspace", "code"], name="unique_tax_code_per_workspace")]

    def __str__(self):
        return self.name
