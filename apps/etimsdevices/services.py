from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.crypto import encrypt
from apps.core.exceptions import BusinessRuleError

from .models import EtimsDevice


@transaction.atomic
def connect(device: EtimsDevice) -> EtimsDevice:
    """Initialise the OSCU with KRA and keep the communication key it returns."""
    from apps.etimssubmissions import client

    if not settings.ETIMS_ENABLED:
        raise BusinessRuleError("eTIMS is switched off for MannaBooks until KRA approval. Your details are saved; connect once it is switched on.")
    if device.pk is None:
        raise BusinessRuleError("Save your KRA PIN, branch id and OSCU serial number first.")
    try:
        info = client.initialise(device)
    except client.EtimsError as exc:
        raise BusinessRuleError(str(exc)) from exc
    if not info.get("cmcKey"):
        raise BusinessRuleError("KRA did not return a communication key. Check the serial number and branch id.")
    device.communication_key_encrypted = encrypt(info["cmcKey"])
    device.sdc_id = info.get("sdcId", "") or ""
    device.mrc_no = info.get("mrcNo", "") or ""
    device.initialised_at = timezone.now()
    device.is_active = True
    device.save()
    return device
