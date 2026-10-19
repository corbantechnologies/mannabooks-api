from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.sequences.services import next_value

from .models import PaymentVoucher, PaymentVoucherLine

S = PaymentVoucher.Status


def suggested_withholding(supplier, lines) -> Decimal:
    """Withholding tax on the VAT-exclusive part of what is paid, at the supplier's rate."""
    rate = supplier.withholding_tax_rate
    if rate is None:
        return ZERO
    base = sum((row["amount"] * (row["bill"].subtotal / row["bill"].total) for row in lines if row["bill"].total), ZERO)
    return q2(base * rate.rate / 100)


@transaction.atomic
def create(workspace, *, supplier, voucher_date, lines: list[dict], withholding_amount=None, notes="", user=None) -> PaymentVoucher:
    if not lines:
        raise BusinessRuleError("Choose at least one bill to pay.")
    for row in lines:
        bill = row["bill"]
        if bill.supplier_id != supplier.id:
            raise BusinessRuleError(f"Bill {bill.supplier_invoice_number} belongs to another supplier.")
        if bill.status not in ("posted", "partially_paid"):
            raise BusinessRuleError(f"Bill {bill.supplier_invoice_number} is not waiting for payment.")
        if row["amount"] <= 0 or row["amount"] > bill.balance_due:
            raise BusinessRuleError(f"Bill {bill.supplier_invoice_number}: pay between 0 and {bill.balance_due:,.2f}.")
    total = sum((q2(r["amount"]) for r in lines), ZERO)
    withholding = suggested_withholding(supplier, lines) if withholding_amount is None else q2(withholding_amount)
    if not ZERO <= withholding < total:
        raise BusinessRuleError("Withholding tax must be less than the amount.")
    voucher = PaymentVoucher.objects.create(workspace=workspace, created_by=user, number=next_value(workspace, "payment_voucher"),
                                            supplier=supplier, voucher_date=voucher_date, total=total, withholding_amount=withholding, notes=notes)
    PaymentVoucherLine.objects.bulk_create(PaymentVoucherLine(voucher=voucher, bill=r["bill"], amount=q2(r["amount"])) for r in lines)
    return voucher


def approve(voucher: PaymentVoucher, user) -> PaymentVoucher:
    if voucher.status != S.DRAFT:
        raise BusinessRuleError("Only a voucher awaiting approval can be approved.")
    from apps.approvalrequests.services import gate

    if not gate("payment_voucher", voucher, user):
        return voucher
    if voucher.created_by_id == user.id and not voucher.workspace.owner_id == user.id:
        raise BusinessRuleError("Someone other than the person who prepared it must approve it.")
    voucher.status, voucher.approved_by, voucher.approved_at = S.APPROVED, user, timezone.now()
    voucher.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return voucher


@transaction.atomic
def pay(voucher: PaymentVoucher, *, payment_date, method, paid_from, reference="", user=None) -> PaymentVoucher:
    from apps.supplierpayments.services import record

    voucher = PaymentVoucher.objects.select_for_update().get(pk=voucher.pk)
    if voucher.status != S.APPROVED:
        raise BusinessRuleError("The voucher must be approved before it is paid.")
    payment = record(voucher.workspace, supplier=voucher.supplier, payment_date=payment_date, amount=voucher.net_payable,
                     withholding_amount=voucher.withholding_amount, method=method, paid_from=paid_from, reference=reference,
                     notes=f"Payment voucher {voucher.number}", allocations=[{"bill": line.bill, "amount": line.amount} for line in voucher.lines.all()],
                     user=user)
    voucher.status, voucher.payment = S.PAID, payment
    voucher.save(update_fields=["status", "payment", "updated_at"])
    return voucher


def cancel(voucher: PaymentVoucher) -> PaymentVoucher:
    if voucher.status not in (S.DRAFT, S.APPROVED):
        raise BusinessRuleError("A paid voucher can't be cancelled. Void its payment instead.")
    voucher.status = S.CANCELLED
    voucher.save(update_fields=["status", "updated_at"])
    return voucher
