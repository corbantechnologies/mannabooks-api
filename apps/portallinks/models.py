import secrets

from django.conf import settings
from django.db import models

from apps.core.models import WorkspaceModel


def new_token() -> str:
    return secrets.token_urlsafe(24)


class PortalLink(WorkspaceModel):
    """A private link a customer opens without signing in, to see an invoice or their statement and pay by M-Pesa."""

    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="portal_links")
    invoice = models.ForeignKey("invoices.Invoice", null=True, blank=True, on_delete=models.CASCADE, related_name="portal_links",
                                help_text="Blank: the customer's statement and all unpaid invoices")
    token = models.CharField(max_length=64, unique=True, default=new_token, editable=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Portal link for {self.customer}"

    @property
    def url(self) -> str:
        return f"{settings.FRONTEND_URL}/p/{self.token}"
