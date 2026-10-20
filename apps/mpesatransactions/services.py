"""
STK prompts and Safaricom callbacks. Callbacks are idempotent: Safaricom may send one more than once.
A completed payment for an invoice (or a C2B payment whose account number is an invoice number) is
recorded as a customer payment at once; anything else waits in the unmatched list.
"""
import logging
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.ledgeraccounts.services import system_account
from apps.mpesaconnections import daraja
from apps.mpesaconnections.models import MpesaConnection

from .models import MpesaTransaction

log = logging.getLogger(__name__)
CANCELLED_CODES = {"1032", "1037"}  # cancelled by the user / phone unreachable


def normalise_phone(phone: str) -> str:
    """07XX..., 01XX..., +2547... or 2547... -> 2547XXXXXXXX (what Daraja expects)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "17":
        digits = "254" + digits
    if not (len(digits) == 12 and digits.startswith("254") and digits[3] in "17"):
        raise BusinessRuleError("Enter a Safaricom number such as 0712 345 678.")
    return digits


def connection_for(workspace) -> MpesaConnection:
    conn = MpesaConnection.objects.filter(workspace=workspace, is_active=True).first()
    if conn is None:
        raise BusinessRuleError("M-Pesa is not connected. Set it up under Organisation > M-Pesa, or enter the M-Pesa code by hand.")
    return conn


def deposit_account(conn):
    return conn.deposit_account or system_account(conn.workspace, "mpesa")


def request_payment(workspace, *, phone: str, amount, invoice=None, reference: str = "", user=None) -> MpesaTransaction:
    """Send an STK prompt to the customer's phone."""
    conn = connection_for(workspace)
    amount = q2(amount)
    if amount < 1:
        raise BusinessRuleError("The amount must be at least KES 1.")
    if amount != amount.to_integral_value():
        raise BusinessRuleError("M-Pesa only takes whole shillings. Round the amount.")
    if invoice is not None:
        if invoice.status not in ("issued", "partially_paid"):
            raise BusinessRuleError("This invoice is not waiting for payment.")
        if amount > invoice.balance_due:
            raise BusinessRuleError(f"The invoice only has {invoice.balance_due:,.2f} left to pay.")
    phone = normalise_phone(phone)
    reference = reference or (invoice.number if invoice else workspace.name)
    try:
        data = daraja.stk_push(conn, phone=phone, amount=int(amount), reference=reference, description="Payment")
    except daraja.DarajaError as exc:
        raise BusinessRuleError(str(exc)) from exc
    return MpesaTransaction.objects.create(
        workspace=workspace, kind=MpesaTransaction.Kind.STK, phone=phone, amount=amount, account_reference=reference[:40],
        checkout_request_id=data.get("CheckoutRequestID", ""), invoice=invoice, created_by=user, raw={"request": data},
    )


def _record_payment(tx: MpesaTransaction, customer, invoice=None, user=None) -> None:
    from apps.payments.services import record

    allocations = []
    if invoice is not None and invoice.status in ("issued", "partially_paid"):
        allocations = [{"invoice": invoice, "amount": min(tx.amount, invoice.balance_due)}]
    tx.payment = record(
        tx.workspace, customer=customer, payment_date=timezone.localdate(tx.paid_at or timezone.now()), amount=tx.amount,
        method="mpesa", reference=tx.mpesa_receipt, deposit_account=deposit_account(MpesaConnection.objects.get(workspace=tx.workspace)),
        notes=f"M-Pesa from {tx.payer_name or tx.phone}".strip(), allocations=allocations, user=user,
    )
    tx.invoice = invoice or tx.invoice
    tx.save(update_fields=["payment", "invoice", "updated_at"])


def _try_match(tx: MpesaTransaction) -> None:
    """Record the payment when we know the invoice. Failures (e.g. a closed month) leave it for a person."""
    from apps.invoices.models import Invoice

    invoice = tx.invoice
    if invoice is None and tx.account_reference:
        invoice = Invoice.objects.filter(workspace=tx.workspace, number__iexact=tx.account_reference.strip(),
                                         status__in=["issued", "partially_paid"]).first()
    if invoice is None:
        return
    try:
        with transaction.atomic():
            _record_payment(tx, invoice.customer, invoice)
    except BusinessRuleError as exc:
        tx.result_description = f"Not applied automatically: {exc}"[:255]
        tx.save(update_fields=["result_description", "updated_at"])


def _items(metadata: dict) -> dict:
    return {i.get("Name"): i.get("Value") for i in (metadata or {}).get("Item", [])}


@transaction.atomic
def handle_stk_callback(conn: MpesaConnection, body: dict) -> None:
    cb = (body.get("Body") or {}).get("stkCallback") or {}
    tx = MpesaTransaction.objects.select_for_update().filter(workspace=conn.workspace, checkout_request_id=cb.get("CheckoutRequestID", "")).first()
    if tx is None or tx.status != MpesaTransaction.Status.PENDING:
        return
    code = str(cb.get("ResultCode", ""))
    tx.result_code, tx.result_description, tx.raw = code, str(cb.get("ResultDesc", ""))[:255], {**tx.raw, "callback": body}
    if code != "0":
        tx.status = MpesaTransaction.Status.CANCELLED if code in CANCELLED_CODES else MpesaTransaction.Status.FAILED
        tx.save()
        return
    items = _items(cb.get("CallbackMetadata"))
    tx.status = MpesaTransaction.Status.COMPLETED
    tx.mpesa_receipt = str(items.get("MpesaReceiptNumber", ""))
    tx.amount = q2(Decimal(str(items.get("Amount", tx.amount))))
    tx.paid_at = _parse_time(items.get("TransactionDate"))
    tx.save()
    _try_match(tx)
    from apps.subscriptions.services import mpesa_settled

    mpesa_settled(tx)


@transaction.atomic
def handle_c2b(conn: MpesaConnection, body: dict) -> MpesaTransaction | None:
    receipt = str(body.get("TransID", "")).strip()
    if not receipt or MpesaTransaction.objects.filter(workspace=conn.workspace, mpesa_receipt=receipt).exists():
        return None
    names = " ".join(str(body.get(k, "")).strip() for k in ("FirstName", "MiddleName", "LastName")).strip()
    tx = MpesaTransaction.objects.create(
        workspace=conn.workspace, kind=MpesaTransaction.Kind.C2B, status=MpesaTransaction.Status.COMPLETED,
        amount=q2(Decimal(str(body.get("TransAmount", "0")))), mpesa_receipt=receipt, phone=str(body.get("MSISDN", ""))[:20],
        payer_name=names[:120], account_reference=str(body.get("BillRefNumber", ""))[:40], paid_at=_parse_time(body.get("TransTime")),
        raw={"confirmation": body},
    )
    _try_match(tx)
    from apps.subscriptions.services import mpesa_settled

    mpesa_settled(tx)
    return tx


@transaction.atomic
def apply(tx: MpesaTransaction, customer, invoice=None, user=None) -> MpesaTransaction:
    """Record an unmatched payment against a customer (and optionally one of their invoices)."""
    tx = MpesaTransaction.objects.select_for_update().get(pk=tx.pk)
    if tx.status != MpesaTransaction.Status.COMPLETED:
        raise BusinessRuleError("Only completed M-Pesa payments can be applied.")
    if tx.is_matched:
        raise BusinessRuleError("This M-Pesa payment is already recorded.")
    if invoice is not None and invoice.customer_id != customer.id:
        raise BusinessRuleError("That invoice belongs to another customer.")
    _record_payment(tx, customer, invoice, user)
    return tx


def _parse_time(value):
    try:
        return timezone.make_aware(datetime.strptime(str(value), "%Y%m%d%H%M%S"))
    except (TypeError, ValueError):
        return timezone.now()


def amount_left(tx) -> Decimal:
    return tx.amount if not tx.is_matched else ZERO


def link_receipt(receipt, transaction_id) -> None:
    """Mark a completed prompt as the payment for a till sale (its code becomes the sale's reference)."""
    tx = MpesaTransaction.objects.select_for_update().filter(workspace=receipt.workspace, pk=transaction_id).first()
    if tx is None or tx.status != MpesaTransaction.Status.COMPLETED:
        raise BusinessRuleError("That M-Pesa payment hasn't completed.")
    if tx.is_matched:
        raise BusinessRuleError("That M-Pesa payment is already used.")
    if tx.amount < receipt.total:
        raise BusinessRuleError(f"The M-Pesa payment ({tx.amount:,.2f}) is less than the sale ({receipt.total:,.2f}).")
    tx.receipt = receipt
    tx.save(update_fields=["receipt", "updated_at"])
    if not receipt.payment_reference:
        receipt.payment_reference = tx.mpesa_receipt
        receipt.save(update_fields=["payment_reference", "updated_at"])
