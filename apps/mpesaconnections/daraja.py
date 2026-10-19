"""
Safaricom Daraja API client, used with each workspace's own credentials. Callback URLs avoid the words
Safaricom rejects in registered URLs (e.g. "mpesa", "safaricom"), so they live under /api/v1/hooks/pay/.
"""
import base64
from datetime import datetime

import requests
from django.conf import settings

from apps.core.crypto import decrypt

TIMEOUT = 30


class DarajaError(Exception):
    pass


def base_url(conn) -> str:
    return settings.MPESA_PRODUCTION_URL if conn.environment == "production" else settings.MPESA_SANDBOX_URL


def callback_url(conn, path: str) -> str:
    return f"{settings.PUBLIC_API_URL}/api/v1/hooks/pay/{conn.callback_token}/{path}"


def _json(res):
    try:
        data = res.json()
    except ValueError as exc:
        raise DarajaError(f"Safaricom answered {res.status_code} without details.") from exc
    if res.status_code >= 400:
        raise DarajaError(data.get("errorMessage") or data.get("ResponseDescription") or f"Safaricom answered {res.status_code}.")
    return data


def access_token(conn) -> str:
    try:
        res = requests.get(f"{base_url(conn)}/oauth/v1/generate", params={"grant_type": "client_credentials"},
                           auth=(decrypt(conn.consumer_key_encrypted), decrypt(conn.consumer_secret_encrypted)), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise DarajaError(f"Safaricom could not be reached: {exc}") from exc
    token = _json(res).get("access_token")
    if not token:
        raise DarajaError("Safaricom did not accept the consumer key and secret.")
    return token


def _post(conn, path: str, body: dict) -> dict:
    try:
        res = requests.post(f"{base_url(conn)}{path}", json=body, headers={"Authorization": f"Bearer {access_token(conn)}"}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise DarajaError(f"Safaricom could not be reached: {exc}") from exc
    return _json(res)


def stk_push(conn, *, phone: str, amount: int, reference: str, description: str) -> dict:
    """Ask the customer's phone to approve a payment. The result arrives later at the stk callback."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{conn.shortcode}{decrypt(conn.passkey_encrypted)}{timestamp}".encode()).decode()
    till = conn.shortcode_type == "till"
    return _post(conn, "/mpesa/stkpush/v1/processrequest", {
        "BusinessShortCode": conn.shortcode, "Password": password, "Timestamp": timestamp,
        "TransactionType": "CustomerBuyGoodsOnline" if till else "CustomerPayBillOnline",
        "Amount": amount, "PartyA": phone, "PartyB": conn.till_number if till else conn.shortcode, "PhoneNumber": phone,
        "CallBackURL": callback_url(conn, "stk/"), "AccountReference": reference[:12], "TransactionDesc": description[:13],
    })


def register_c2b(conn) -> dict:
    """Ask Safaricom to tell MannaBooks about every payment made straight to the paybill or till."""
    return _post(conn, "/mpesa/c2b/v1/registerurl", {
        "ShortCode": conn.till_number if conn.shortcode_type == "till" else conn.shortcode, "ResponseType": "Completed",
        "ConfirmationURL": callback_url(conn, "c2b/confirmation/"), "ValidationURL": callback_url(conn, "c2b/validation/"),
    })
