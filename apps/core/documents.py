"""
Abstract models shared by sales documents (invoices, cash sales, credit notes, quotations). Each
document app defines its own concrete model and line model from these, so every document has the same
customer, currency, totals and line fields.
"""
from django.db import models

from apps.core.models import BaseModel, WorkspaceModel
from apps.core.money import MONEY_FIELD, RATE_FIELD


class SalesDocument(WorkspaceModel):
    number = models.CharField(max_length=30, blank=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="%(app_label)s")
    issue_date = models.DateField()
    currency = models.CharField(max_length=3)
    exchange_rate = models.DecimalField(**RATE_FIELD, default=1, help_text="1 unit of the document currency in the base currency")
    prices_include_tax = models.BooleanField(default=False, help_text="Unit prices already include VAT")
    reference = models.CharField(max_length=60, blank=True, help_text="Customer's order or LPO number")
    notes = models.TextField(blank=True)
    subtotal = models.DecimalField(**MONEY_FIELD, default=0)
    tax_total = models.DecimalField(**MONEY_FIELD, default=0)
    total = models.DecimalField(**MONEY_FIELD, default=0)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cost_center = models.ForeignKey("costcenters.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True
        ordering = ["-issue_date", "-created_at"]

    def __str__(self):
        return self.number or f"Draft {self.issue_date}"


class EtimsFields(models.Model):
    """What KRA eTIMS returns when a document is signed. Empty while signing is switched off."""

    class EtimsStatus(models.TextChoices):
        NONE = "", "Not sent"
        DISABLED = "disabled", "Signing switched off"
        NOT_CONFIGURED = "not_configured", "Device not set up"
        PENDING = "pending", "Waiting for KRA"
        SIGNED = "signed", "Signed by KRA"
        FAILED = "failed", "KRA rejected it"

    etims_status = models.CharField(max_length=20, choices=EtimsStatus.choices, blank=True, default="")
    etims_cu_invoice_number = models.CharField(max_length=60, blank=True)
    etims_signature = models.CharField(max_length=200, blank=True)
    etims_qr_url = models.URLField(max_length=500, blank=True)
    etims_signed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class SalesLine(BaseModel):
    product = models.ForeignKey("products.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0,
                                          help_text="A fixed discount on the line, e.g. loyalty points redeemed")
    tax_rate = models.ForeignKey("taxrates.TaxRate", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    net_amount = models.DecimalField(**MONEY_FIELD, default=0)
    tax_amount = models.DecimalField(**MONEY_FIELD, default=0)
    total_amount = models.DecimalField(**MONEY_FIELD, default=0)
    line_no = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["line_no"]


class PurchaseLine(BaseModel):
    """One line of a purchase document: what is bought, at what cost, and where the cost is recorded."""

    product = models.ForeignKey("products.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    tax_rate = models.ForeignKey("taxrates.TaxRate", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    account = models.ForeignKey("ledgeraccounts.LedgerAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                help_text="Blank for stock items: they go to Inventory")
    net_amount = models.DecimalField(**MONEY_FIELD, default=0)
    tax_amount = models.DecimalField(**MONEY_FIELD, default=0)
    total_amount = models.DecimalField(**MONEY_FIELD, default=0)
    line_no = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["line_no"]


class PurchaseDocument(WorkspaceModel):
    """Supplier, totals and VAT basis shared by purchase orders, service orders and bills."""

    number = models.CharField(max_length=30, blank=True)
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT, related_name="%(app_label)s")
    prices_include_tax = models.BooleanField(default=False)
    reference = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    subtotal = models.DecimalField(**MONEY_FIELD, default=0)
    tax_total = models.DecimalField(**MONEY_FIELD, default=0)
    total = models.DecimalField(**MONEY_FIELD, default=0)
    cost_center = models.ForeignKey("costcenters.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        abstract = True

    def __str__(self):
        return self.number or "Draft"
