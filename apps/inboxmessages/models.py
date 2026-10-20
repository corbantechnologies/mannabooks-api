from django.conf import settings
from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class InboxMessage(WorkspaceModel):
    """
    A document one MannaBooks business sent straight to another (matched by KRA PIN): an invoice, a quotation or
    a purchase order. `workspace` is the business receiving it. Accepting it creates the matching draft on their side:
    a bill for an invoice, a purchase order for a quotation, an invoice for a purchase order.
    """

    class Kind(models.TextChoices):
        INVOICE = "invoice", "Invoice"
        QUOTATION = "quotation", "Quotation"
        PURCHASE_ORDER = "purchase_order", "Purchase order (LPO)"

    class Status(models.TextChoices):
        NEW = "new", "New"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    sender = models.ForeignKey("workspaces.Workspace", on_delete=models.CASCADE, related_name="sent_inbox_messages")
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    sender_name = models.CharField(max_length=200)
    sender_kra_pin = models.CharField(max_length=20, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    source_id = models.UUIDField(help_text="The document in the sender's workspace")
    number = models.CharField(max_length=40)
    document_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="KES")
    prices_include_tax = models.BooleanField(default=False)
    subtotal = models.DecimalField(**MONEY_FIELD, default=0)
    tax_total = models.DecimalField(**MONEY_FIELD, default=0)
    total = models.DecimalField(**MONEY_FIELD, default=0)
    lines = models.JSONField(default=list, help_text="description, quantity, unit, unit_price, tax_code, net, tax, total")
    message = models.TextField(blank=True, help_text="A note from the sender")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    read_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.CharField(max_length=255, blank=True)
    created_type = models.CharField(max_length=20, blank=True, help_text="What accepting it created: bill, purchase_order or invoice")
    created_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.number} from {self.sender_name}"
