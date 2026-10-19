from django.db import transaction

from apps.core import sales
from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.core.sales_views import check_customer, default_currency
from apps.journals.services import replace_for_source
from apps.payments.services import DEPOSIT_SUBTYPES
from apps.sequences.services import next_value

from .models import Receipt, ReceiptLine

SOURCE = {"source": "receipt", "source_model": "receipts.Receipt"}


@transaction.atomic
def create(workspace, *, header: dict, rows: list[dict], method: str, deposit_account=None, payment_reference="",
           customer_name="", customer_pin="", shift=None, mpesa_prompt=False, redeem_points=0, user=None) -> Receipt:
    customer = header.get("customer")
    check_customer(customer)
    if shift is not None:
        if shift.status != "open":
            raise BusinessRuleError("This shift is closed. Open a new shift to sell.")
        if user is not None and shift.cashier_id != user.id:
            raise BusinessRuleError("This is another cashier's shift.")
        deposit_account = deposit_account or shift.register.account_for(method)
        header.setdefault("branch", shift.register.branch)
    if deposit_account is None:
        from apps.ledgeraccounts.services import system_account

        deposit_account = system_account(workspace, {"cash": "cash", "mpesa": "mpesa"}.get(method, "bank"))
    if deposit_account.subtype not in DEPOSIT_SUBTYPES or not deposit_account.is_active:
        raise BusinessRuleError("Choose a cash, bank or M-Pesa account to receive the money into.")
    if method == "mpesa" and not payment_reference.strip() and not mpesa_prompt:
        raise BusinessRuleError("Enter the M-Pesa transaction code.")
    receipt = Receipt(
        workspace=workspace, created_by=user, currency=header.get("currency") or default_currency(workspace, customer),
        method=method, deposit_account=deposit_account, payment_reference=payment_reference.strip(), shift=shift,
        customer_name=(customer_name or (customer.name if customer else "")).strip(), customer_pin=customer_pin.strip().upper(),
        **{k: v for k, v in header.items() if k != "currency"},
    )
    receipt.exchange_rate = sales.document_rate(workspace, receipt.currency, receipt.issue_date)
    receipt.number = next_value(workspace, "receipt")
    receipt.save()
    from apps.loyaltytransactions import services as loyalty

    lines = loyalty.discount_lines(workspace, customer, sales.resolve_lines(workspace, rows, customer=customer), receipt.prices_include_tax, redeem_points)
    sales.write_lines(receipt, ReceiptLine, "receipt", lines)
    if receipt.total <= ZERO:
        raise BusinessRuleError("A cash sale needs at least one line with a value.")
    lines = list(receipt.lines.select_related("account", "tax_rate__sales_account"))
    replace_for_source(
        workspace, **SOURCE, source_id=str(receipt.pk), entry_date=receipt.issue_date, reference=receipt.number,
        description=f"Cash sale {receipt.number}" + (f" to {receipt.customer_name}" if receipt.customer_name else ""),
        lines=sales.posting_lines(receipt, lines, deposit_account, label=f"Cash sale {receipt.number}"), user=user,
    )
    from apps.etimssubmissions.services import request_signing

    request_signing(receipt, "receipt")
    from apps.stockmovements import sales as stock

    stock.issue(receipt, "receipt", user)
    loyalty.after_sale(receipt, "receipt", redeem_points)
    return receipt


@transaction.atomic
def void(receipt: Receipt, reason: str, user=None) -> Receipt:
    if receipt.status == Receipt.Status.VOID:
        raise BusinessRuleError("This cash sale is already void.")
    if receipt.etims_status == "signed":
        raise BusinessRuleError("KRA has signed this sale. Issue a credit note instead of voiding it.")
    replace_for_source(receipt.workspace, **SOURCE, source_id=str(receipt.pk), entry_date=receipt.issue_date,
                       description="", lines=[], user=user)
    receipt.status, receipt.void_reason = Receipt.Status.VOID, reason[:255]
    receipt.save(update_fields=["status", "void_reason", "updated_at"])
    from apps.loyaltytransactions.services import reverse_document
    from apps.stockmovements import sales as stock

    reverse_document(receipt)
    stock.give_back(receipt, "receipt", user)
    return receipt
