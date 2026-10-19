from django.db import transaction

from apps.bills.models import Bill
from apps.bills.services import refresh_paid
from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.sequences.services import next_value

from .models import SupplierPayment, SupplierPaymentAllocation

SOURCE = {"source": "supplier_payment", "source_model": "supplierpayments.SupplierPayment"}


@transaction.atomic
def record(workspace, *, supplier, payment_date, amount, method, paid_from, withholding_amount=ZERO, reference="", notes="",
           allocations=None, user=None) -> SupplierPayment:
    amount, withholding = q2(amount), q2(withholding_amount or 0)
    if amount <= 0:
        raise BusinessRuleError("The amount must be more than zero.")
    if withholding < 0:
        raise BusinessRuleError("Withholding tax can't be negative.")
    if paid_from.subtype not in ("cash", "bank") or not paid_from.is_active:
        raise BusinessRuleError("Pay from a cash, bank or M-Pesa account.")
    if method in ("mpesa", "cheque") and not reference.strip():
        raise BusinessRuleError("Enter the M-Pesa code or cheque number.")
    payment = SupplierPayment.objects.create(
        workspace=workspace, created_by=user, number=next_value(workspace, "supplier_payment"), supplier=supplier, payment_date=payment_date,
        amount=amount, withholding_amount=withholding, method=method, reference=reference.strip(), paid_from=paid_from, notes=notes,
        unallocated_amount=amount + withholding,
    )
    label = f"Payment {payment.number} to {supplier}"
    lines = [LineInput(account=system_account(workspace, "payable"), debit=amount + withholding, description=label),
             LineInput(account=paid_from, credit=amount, description=label)]
    if withholding:
        lines.append(LineInput(account=system_account(workspace, "wht_payable"), credit=withholding, description=f"{label}: withholding tax"))
    replace_for_source(workspace, **SOURCE, source_id=str(payment.pk), entry_date=payment_date, reference=payment.number,
                       description=label, lines=lines, user=user)
    if allocations:
        allocate(payment, allocations)
    return payment


@transaction.atomic
def allocate(payment: SupplierPayment, allocations: list[dict]) -> SupplierPayment:
    payment = SupplierPayment.objects.select_for_update().get(pk=payment.pk)
    if payment.status != SupplierPayment.Status.POSTED:
        raise BusinessRuleError("This payment is void.")
    total = ZERO
    for row in allocations:
        bill, amount = Bill.objects.select_for_update().get(pk=row["bill"].pk), q2(row["amount"])
        if amount <= 0:
            continue
        if bill.supplier_id != payment.supplier_id:
            raise BusinessRuleError(f"Bill {bill.supplier_invoice_number} belongs to another supplier.")
        if bill.status not in (Bill.Status.POSTED, Bill.Status.PARTIALLY_PAID):
            raise BusinessRuleError(f"Bill {bill.supplier_invoice_number} is {bill.get_status_display().lower()}.")
        if amount > bill.balance_due:
            raise BusinessRuleError(f"Bill {bill.supplier_invoice_number} only has {bill.balance_due:,.2f} left to pay.")
        total += amount
        if total > payment.unallocated_amount:
            raise BusinessRuleError(f"You applied more than the {payment.unallocated_amount:,.2f} available.")
        alloc, created = SupplierPaymentAllocation.objects.get_or_create(payment=payment, bill=bill, defaults={"amount": amount})
        if not created:
            alloc.amount += amount
            alloc.save(update_fields=["amount", "updated_at"])
        refresh_paid(bill)
    payment.unallocated_amount -= total
    payment.save(update_fields=["unallocated_amount", "updated_at"])
    return payment


@transaction.atomic
def void(payment: SupplierPayment, reason: str, user=None) -> SupplierPayment:
    if payment.status == SupplierPayment.Status.VOID:
        raise BusinessRuleError("This payment is already void.")
    replace_for_source(payment.workspace, **SOURCE, source_id=str(payment.pk), entry_date=payment.payment_date, description="", lines=[], user=user)
    payment.status, payment.void_reason, payment.unallocated_amount = SupplierPayment.Status.VOID, reason[:255], ZERO
    payment.save(update_fields=["status", "void_reason", "unallocated_amount", "updated_at"])
    for alloc in payment.allocations.select_related("bill"):
        refresh_paid(alloc.bill)
    from apps.paymentvouchers.models import PaymentVoucher

    PaymentVoucher.objects.filter(payment=payment).update(status="approved", payment=None)
    return payment
