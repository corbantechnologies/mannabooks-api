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

    class Meta(SalesDocument.Meta):
        pass


class QuotationLine(SalesLine):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="lines")
