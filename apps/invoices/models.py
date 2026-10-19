from django.conf import settings
from django.db import models

from apps.core.documents import EtimsFields, SalesDocument, SalesLine
from apps.core.money import MONEY_FIELD


class Invoice(SalesDocument, EtimsFields):
    """
    A sale on credit, or a debit note (an extra charge against an earlier invoice). Drafts can be edited;
    issuing numbers it, posts it and sends it to KRA eTIMS.
    """

    class Kind(models.TextChoices):
        INVOICE = "invoice", "Invoice"
        DEBIT_NOTE = "debit_note", "Debit note"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.INVOICE,
                            help_text="A debit note charges more against an earlier invoice; KRA treats it as a sale")
    original_invoice = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="debit_notes")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    due_date = models.DateField()
    amount_paid = models.DecimalField(**MONEY_FIELD, default=0, help_text="Payments and credit notes applied")
    balance_due = models.DecimalField(**MONEY_FIELD, default=0)
    quotation = models.ForeignKey("quotations.Quotation", null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices")
    issued_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta(SalesDocument.Meta):
        indexes = [models.Index(fields=["workspace", "status"]), models.Index(fields=["workspace", "customer"])]


class InvoiceLine(SalesLine):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
