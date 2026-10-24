from django.db import models

from apps.core.documents import SalesDocument, SalesLine


class Quotation(SalesDocument):
    """A price offer. Nothing is posted; an accepted quotation converts into a draft invoice."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CONVERTED = "converted", "Converted to invoice"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    valid_until = models.DateField()
    catalogue = models.ForeignKey("catalogues.Catalogue", null=True, blank=True, on_delete=models.SET_NULL, related_name="quotations",
                                  help_text="Set when the client wrote it by picking from a shared catalogue")
    public_token = models.CharField(max_length=40, null=True, blank=True, unique=True, help_text="The client's private link to the quote")
    contact_email = models.EmailField(blank=True, db_default="", help_text="Where the client asked for the quote to go")

    class Meta(SalesDocument.Meta):
        pass


class QuotationLine(SalesLine):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="lines")
