from django.db import transaction
from django.utils import timezone

from .models import Sequence

# Defaults used the first time a workspace numbers something. Each module adds its own.
DEFAULTS = {
    "employee": {"prefix": "EMP-", "padding": 4, "include_year": False},
    "journal": {"prefix": "JE-", "padding": 4, "include_year": True},
    "customer": {"prefix": "CUS-", "padding": 4, "include_year": False},
    "quotation": {"prefix": "QT-", "padding": 4, "include_year": True},
    "invoice": {"prefix": "INV-", "padding": 4, "include_year": True},
    "payment": {"prefix": "PAY-", "padding": 4, "include_year": True},
    "receipt": {"prefix": "RCT-", "padding": 4, "include_year": True},
    "credit_note": {"prefix": "CN-", "padding": 4, "include_year": True},
    "debit_note": {"prefix": "DBN-", "padding": 4, "include_year": True},
    "delivery_note": {"prefix": "DN-", "padding": 4, "include_year": True},
    "pos_shift": {"prefix": "SH-", "padding": 4, "include_year": True},
    "loyalty_member": {"prefix": "LC-", "padding": 6, "include_year": False},
    "supplier": {"prefix": "SUP-", "padding": 4, "include_year": False},
    "purchase_order": {"prefix": "PO-", "padding": 4, "include_year": True},
    "service_order": {"prefix": "SO-", "padding": 4, "include_year": True},
    "goods_receipt": {"prefix": "GRN-", "padding": 4, "include_year": True},
    "service_completion": {"prefix": "SC-", "padding": 4, "include_year": True},
    "bill": {"prefix": "BILL-", "padding": 4, "include_year": True},
    "payment_voucher": {"prefix": "PV-", "padding": 4, "include_year": True},
    "supplier_payment": {"prefix": "SPAY-", "padding": 4, "include_year": True},
    "stock_transfer": {"prefix": "TRF-", "padding": 4, "include_year": True},
    "stock_adjustment": {"prefix": "ADJ-", "padding": 4, "include_year": True},
    "stock_take": {"prefix": "ST-", "padding": 4, "include_year": True},
    "production_order": {"prefix": "MO-", "padding": 4, "include_year": True},
    "expense": {"prefix": "EXP-", "padding": 4, "include_year": True},
    "other_income": {"prefix": "OI-", "padding": 4, "include_year": True},
    "bank_transfer": {"prefix": "BT-", "padding": 4, "include_year": True},
    "project": {"prefix": "PRJ-", "padding": 4, "include_year": False},
    "fixed_asset": {"prefix": "FA-", "padding": 4, "include_year": False},
    "product": {"prefix": "SKU-", "padding": 5, "include_year": False},
    "department": {"prefix": "DEP-", "padding": 3, "include_year": False},
    "cost_center": {"prefix": "CC-", "padding": 3, "include_year": False},
    "branch": {"prefix": "BR-", "padding": 2, "include_year": False},
    "warehouse": {"prefix": "WH-", "padding": 2, "include_year": False},
    "lead": {"prefix": "LD-", "padding": 4, "include_year": False},
    "deal": {"prefix": "DL-", "padding": 4, "include_year": False},
    "online_order": {"prefix": "WEB-", "padding": 4, "include_year": True},
}


@transaction.atomic
def next_value(workspace, key: str) -> str:
    """Take the next number for `key` in this workspace. Locked, so two requests never share one."""
    defaults = DEFAULTS.get(key, {"prefix": f"{key[:3].upper()}-", "padding": 4, "include_year": False})
    Sequence.objects.get_or_create(workspace=workspace, key=key, defaults=defaults)
    seq = Sequence.objects.select_for_update().get(workspace=workspace, key=key)
    year = timezone.localdate().year
    if seq.include_year and seq.current_year != year:
        seq.current_year, seq.next_number = year, 1
    number = seq.next_number
    seq.next_number = number + 1
    seq.save(update_fields=["next_number", "current_year", "updated_at"])
    return seq.format(number, year)
