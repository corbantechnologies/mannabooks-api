from django.db import models

from apps.core.models import WorkspaceModel


class PaymentOption(WorkspaceModel):
    """How customers can pay the business, printed on invoices and quotations: a bank account, M-Pesa paybill or till, Pochi."""

    class Kind(models.TextChoices):
        BANK = "bank", "Bank account"
        PAYBILL = "mpesa_paybill", "M-Pesa paybill"
        TILL = "mpesa_till", "M-Pesa till (Buy Goods)"
        POCHI = "pochi", "Pochi la Biashara"
        OTHER = "other", "Other"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    bank_name = models.CharField(max_length=100, blank=True)
    branch = models.CharField(max_length=100, blank=True)
    account_name = models.CharField(max_length=150, blank=True)
    account_number = models.CharField(max_length=60, blank=True, help_text="Bank account number, or the paybill account number")
    swift_code = models.CharField(max_length=20, blank=True)
    number = models.CharField(max_length=30, blank=True, help_text="Paybill or till number, or the Pochi phone number")
    instructions = models.CharField(max_length=255, blank=True)
    show_on_documents = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.get_kind_display()

    def lines(self) -> list[str]:
        """What prints on a document. A paybill without its own account number asks for the document number."""
        k = self.Kind
        if self.kind == k.BANK:
            out = [f"Bank: {self.bank_name}" + (f", {self.branch} branch" if self.branch else "")]
            out += [f"Account name: {self.account_name}"] if self.account_name else []
            out += [f"Account number: {self.account_number}"] if self.account_number else []
            out += [f"SWIFT: {self.swift_code}"] if self.swift_code else []
        elif self.kind == k.PAYBILL:
            out = [f"M-Pesa paybill: {self.number}", f"Account: {self.account_number or 'the document number'}"]
        elif self.kind == k.TILL:
            out = [f"M-Pesa Buy Goods till: {self.number}"]
        elif self.kind == k.POCHI:
            out = [f"Pochi la Biashara: {self.number}"]
        else:
            out = []
        return out + ([self.instructions] if self.instructions else [])
