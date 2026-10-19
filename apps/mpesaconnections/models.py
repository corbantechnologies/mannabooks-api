import secrets

from django.db import models

from apps.core.models import WorkspaceModel


def new_token() -> str:
    return secrets.token_urlsafe(24)


class MpesaConnection(WorkspaceModel):
    """
    A business's own Safaricom Daraja app, so M-Pesa money goes straight to its paybill or till.
    Secrets are stored encrypted. `callback_token` identifies the workspace in Safaricom's callbacks.
    """

    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "Daraja sandbox (testing)"
        PRODUCTION = "production", "Production"

    class ShortcodeType(models.TextChoices):
        PAYBILL = "paybill", "Paybill"
        TILL = "till", "Till (Buy Goods)"

    environment = models.CharField(max_length=12, choices=Environment.choices, default=Environment.SANDBOX)
    shortcode_type = models.CharField(max_length=10, choices=ShortcodeType.choices, default=ShortcodeType.PAYBILL)
    shortcode = models.CharField(max_length=20, help_text="Paybill number, or the store number for a till")
    till_number = models.CharField(max_length=20, blank=True, help_text="Tills only: the till customers pay to")
    consumer_key_encrypted = models.TextField(blank=True)
    consumer_secret_encrypted = models.TextField(blank=True)
    passkey_encrypted = models.TextField(blank=True)
    deposit_account = models.ForeignKey("ledgeraccounts.LedgerAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                        help_text="Blank: the M-Pesa account")
    callback_token = models.CharField(max_length=64, unique=True, default=new_token, editable=False)
    is_active = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    c2b_registered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_mpesa_connection_per_workspace")]

    def __str__(self):
        return f"{self.get_shortcode_type_display()} {self.till_number or self.shortcode}"
