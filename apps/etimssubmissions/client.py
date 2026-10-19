"""
HTTP client for KRA eTIMS OSCU. It is only called when eTIMS signing is switched on for the platform
(ETIMS_ENABLED), which stays off until KRA approves MannaBooks. The request shapes follow KRA's OSCU
specification and must be verified against the KRA sandbox before the switch is turned on.
"""
import requests
from django.conf import settings

from apps.core.crypto import decrypt

TIMEOUT = 20


class EtimsError(Exception):
    pass


def _base_url(device) -> str:
    return settings.ETIMS_PRODUCTION_URL if device.environment == "production" else settings.ETIMS_SANDBOX_URL


def _post(device, path: str, body: dict, *, with_key: bool = True) -> dict:
    headers = {"tin": device.kra_pin, "bhfId": device.branch_code, "Content-Type": "application/json"}
    if with_key:
        headers["cmcKey"] = decrypt(device.communication_key_encrypted)
    try:
        res = requests.post(f"{_base_url(device)}{path}", json=body, headers=headers, timeout=TIMEOUT)
        data = res.json()
    except (requests.RequestException, ValueError) as exc:
        raise EtimsError(f"KRA eTIMS could not be reached: {exc}") from exc
    if str(data.get("resultCd")) != "000":
        raise EtimsError(f"KRA eTIMS answered {data.get('resultCd')}: {data.get('resultMsg', 'no message')}")
    return data


def initialise(device) -> dict:
    """OSCU initialisation: KRA answers with the branch's control unit details and communication key."""
    data = _post(device, "/initializer/selectInitInfo",
                 {"tin": device.kra_pin, "bhfId": device.branch_code, "dvcSrlNo": device.device_serial}, with_key=False)
    return (data.get("data") or {}).get("info") or {}


def save_sale(device, payload: dict) -> dict:
    return _post(device, "/trnsSales/saveSales", payload)
