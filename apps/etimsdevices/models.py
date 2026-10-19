from django.db import models

from apps.core.models import WorkspaceModel


class EtimsDevice(WorkspaceModel):
    """
    A workspace's KRA eTIMS OSCU connection. OSCU is software (no physical box): when the business applies
    for OSCU on the KRA eTIMS portal, KRA gives it a "device" serial number for its branch. MannaBooks
    then initialises it with KRA (`connect`), which returns the communication key used to sign documents.

    Details can be saved at any time; nothing is sent to KRA while eTIMS signing is switched off for the
    whole platform (ETIMS_ENABLED, until KRA approves MannaBooks).
    """

    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "KRA sandbox (testing)"
        PRODUCTION = "production", "KRA production"

    kra_pin = models.CharField("KRA PIN", max_length=20)
    branch_code = models.CharField(max_length=4, default="00", help_text="KRA branch id, 00 for head office")
    device_serial = models.CharField(max_length=60)
    environment = models.CharField(max_length=12, choices=Environment.choices, default=Environment.SANDBOX)
    communication_key_encrypted = models.TextField(blank=True)
    sdc_id = models.CharField(max_length=60, blank=True, help_text="Given by KRA when the device is initialised")
    mrc_no = models.CharField(max_length=60, blank=True)
    last_invoice_number = models.PositiveIntegerField(default=0, help_text="KRA needs an unbroken sequence")
    is_active = models.BooleanField(default=False)
    initialised_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace"], name="one_etims_device_per_workspace")]

    def __str__(self):
        return f"{self.kra_pin} / {self.device_serial}"
