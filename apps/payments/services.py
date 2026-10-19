from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.invoices.models import Invoice
from apps.invoices.services import refresh_paid
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.sequences.services import next_value

from .models import Payment, PaymentAllocation

SOURCE = {"source": "payment", "source_model": "payments.Payment"}
DEPOSIT_SUBTYPES = ("cash", "bank")


def _check_allocations(payment: Payment, allocations: list[dict], available) -> list[tuple[Invoice, object]]:
    checked, total = [], ZERO
    for row in allocations:
        invoice, amount = row["invoice"], q2(row["amount"])
        if amount <= ZERO:
            continue
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.workspace_id != payment.workspace_id or invoice.customer_id != payment.customer_id:
            raise BusinessRuleError(f"Invoice {invoice.number or 'draft'} belongs to another customer.")
        if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.PARTIALLY_PAID):
            raise BusinessRuleError(f"Invoice {invoice.number or 'draft'} is {invoice.get_status_display().lower()}; it can't take a payment.")
        if invoice.currency != payment_currency(payment):
            raise BusinessRuleError(f"Invoice {invoice.number} is in {invoice.currency}; record its payment in the same currency.")
        if amount > invoice.balance_due:
            raise BusinessRuleError(f"Invoice {invoice.number} only has {invoice.balance_due:,.2f} left to pay.")
        total += amount
        checked.append((invoice, amount))
    if total > available:
        raise BusinessRuleError(f"You applied {total:,.2f} but only {available:,.2f} is available.")
    return checked


def payment_currency(payment: Payment) -> str:
    from apps.currencies.services import base_currency

    return base_currency(payment.workspace).code


@transaction.atomic
def record(workspace, *, customer, payment_date, amount, method, deposit_account, reference="", notes="",
           allocations=None, user=None) -> Payment:
    amount = q2(amount)
    if amount <= ZERO:
        raise BusinessRuleError("The amount must be more than zero.")
    if not customer.is_active:
        raise BusinessRuleError(f"{customer} is inactive.")
    if deposit_account.subtype not in DEPOSIT_SUBTYPES or not deposit_account.is_active:
        raise BusinessRuleError("Choose a cash, bank or M-Pesa account to receive the money into.")
    if method == "mpesa" and not reference.strip():
        raise BusinessRuleError("Enter the M-Pesa transaction code.")
    payment = Payment.objects.create(
        workspace=workspace, number=next_value(workspace, "payment"), customer=customer, payment_date=payment_date,
        amount=amount, method=method, reference=reference.strip().upper() if method == "mpesa" else reference.strip(),
        deposit_account=deposit_account, notes=notes, unallocated_amount=amount, created_by=user,
    )
    replace_for_source(
        workspace, **SOURCE, source_id=str(payment.pk), entry_date=payment_date, reference=payment.number,
        description=f"Payment {payment.number} from {customer}",
        lines=[
            LineInput(account=deposit_account, debit=amount, description=f"Payment {payment.number}"),
            LineInput(account=system_account(workspace, "receivable"), credit=amount, description=f"Payment {payment.number}"),
        ],
        user=user,
    )
    if allocations:
        allocate(payment, allocations)
    return payment


@transaction.atomic
def allocate(payment: Payment, allocations: list[dict]) -> Payment:
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status != Payment.Status.POSTED:
        raise BusinessRuleError("This payment is void.")
    for invoice, amount in _check_allocations(payment, allocations, payment.unallocated_amount):
        alloc, created = PaymentAllocation.objects.get_or_create(payment=payment, invoice=invoice, defaults={"amount": amount})
        if not created:
            alloc.amount += amount
            alloc.save(update_fields=["amount", "updated_at"])
        payment.unallocated_amount -= amount
        refresh_paid(invoice)
    payment.save(update_fields=["unallocated_amount", "updated_at"])
    return payment


@transaction.atomic
def void(payment: Payment, reason: str, user=None) -> Payment:
    if payment.status == Payment.Status.VOID:
        raise BusinessRuleError("This payment is already void.")
    replace_for_source(payment.workspace, **SOURCE, source_id=str(payment.pk), entry_date=payment.payment_date,
                       description="", lines=[], user=user)
    payment.status, payment.void_reason, payment.unallocated_amount = Payment.Status.VOID, reason[:255], ZERO
    payment.save(update_fields=["status", "void_reason", "unallocated_amount", "updated_at"])
    for alloc in payment.allocations.select_related("invoice"):
        refresh_paid(alloc.invoice)
    return payment
