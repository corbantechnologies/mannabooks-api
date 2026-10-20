from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core import sales
from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.core.sales_views import check_customer, default_currency
from apps.journals.services import replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.sequences.services import next_value

from .models import Invoice, InvoiceLine

SOURCE = {"source": "invoice", "source_model": "invoices.Invoice"}


@transaction.atomic
def save_draft(workspace, *, header: dict, rows: list[dict] | None, user=None, invoice: Invoice | None = None) -> Invoice:
    if invoice is not None and invoice.status != Invoice.Status.DRAFT:
        raise BusinessRuleError("Only draft invoices can be edited. Use a credit note to correct an issued invoice.")
    customer = header.get("customer", invoice.customer if invoice else None)
    if customer is None:
        raise BusinessRuleError("Choose a customer.")
    check_customer(customer)
    original = header.get("original_invoice", invoice.original_invoice if invoice else None)
    if header.get("kind", invoice.kind if invoice else Invoice.Kind.INVOICE) == Invoice.Kind.DEBIT_NOTE:
        if original is None:
            raise BusinessRuleError("Choose the invoice this debit note adds to.")
        if original.customer_id != customer.id or original.kind != Invoice.Kind.INVOICE:
            raise BusinessRuleError("A debit note must add to an invoice of the same customer.")
        if original.status in (Invoice.Status.DRAFT, Invoice.Status.VOID):
            raise BusinessRuleError("The original invoice must be issued.")
    elif original is not None:
        raise BusinessRuleError("Only a debit note refers to an original invoice.")
    issue_date = header.get("issue_date") or (invoice.issue_date if invoice else timezone.localdate())
    if invoice is None:
        from apps.subscriptions.services import check_documents

        check_documents(workspace)
        invoice = Invoice(workspace=workspace, created_by=user, customer=customer, issue_date=issue_date,
                          currency=header.get("currency") or default_currency(workspace, customer),
                          due_date=header.get("due_date") or issue_date + timedelta(days=customer.payment_terms_days))
    for key, value in header.items():
        setattr(invoice, key, value)
    if "due_date" not in header and "issue_date" in header and invoice.pk is None:
        invoice.due_date = issue_date + timedelta(days=customer.payment_terms_days)
    if invoice.due_date < invoice.issue_date:
        raise BusinessRuleError("The due date can't be before the invoice date.")
    invoice.save()
    if rows is not None:
        sales.write_lines(invoice, InvoiceLine, "invoice", sales.resolve_lines(workspace, rows, customer=invoice.customer))
    invoice.balance_due = invoice.total
    invoice.save(update_fields=["balance_due", "updated_at"])
    return invoice


@transaction.atomic
def issue(invoice: Invoice, user=None) -> Invoice:
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != Invoice.Status.DRAFT:
        raise BusinessRuleError("This invoice is already issued.")
    lines = list(invoice.lines.select_related("account", "tax_rate__sales_account"))
    if not lines or invoice.total <= ZERO:
        raise BusinessRuleError("Add at least one line with a value before issuing.")
    check_customer(invoice.customer)
    invoice.exchange_rate = sales.document_rate(invoice.workspace, invoice.currency, invoice.issue_date)
    debit = invoice.kind == Invoice.Kind.DEBIT_NOTE
    invoice.number = next_value(invoice.workspace, "debit_note" if debit else "invoice")
    invoice.status = Invoice.Status.ISSUED
    invoice.issued_at, invoice.issued_by = timezone.now(), user
    invoice.amount_paid, invoice.balance_due = ZERO, invoice.total
    invoice.save()
    receivable = system_account(invoice.workspace, "receivable")
    replace_for_source(
        invoice.workspace, **SOURCE, source_id=str(invoice.pk), entry_date=invoice.issue_date,
        description=f"{invoice.get_kind_display()} {invoice.number} to {invoice.customer}", reference=invoice.number,
        lines=sales.posting_lines(invoice, lines, receivable, label=f"{invoice.get_kind_display()} {invoice.number}"), user=user,
    )
    from apps.etimssubmissions.services import request_signing

    request_signing(invoice, "invoice")
    if invoice.kind == Invoice.Kind.INVOICE:
        from apps.stockmovements import sales as stock

        stock.issue(invoice, "invoice", user)
    from apps.loyaltytransactions.services import after_sale

    after_sale(invoice, "invoice")
    return invoice


@transaction.atomic
def void(invoice: Invoice, reason: str, user=None) -> Invoice:
    if invoice.status == Invoice.Status.VOID:
        raise BusinessRuleError("This invoice is already void.")
    if invoice.status == Invoice.Status.DRAFT:
        raise BusinessRuleError("Delete a draft instead of voiding it.")
    if invoice.amount_paid > ZERO:
        raise BusinessRuleError("Payments or credit notes are applied to this invoice. Remove them first.")
    if invoice.etims_status == "signed":
        raise BusinessRuleError("KRA has signed this invoice. Issue a credit note instead of voiding it.")
    replace_for_source(invoice.workspace, **SOURCE, source_id=str(invoice.pk), entry_date=invoice.issue_date,
                       description="", lines=[], user=user)
    invoice.status, invoice.void_reason, invoice.balance_due = Invoice.Status.VOID, reason[:255], ZERO
    invoice.save(update_fields=["status", "void_reason", "balance_due", "updated_at"])
    from apps.loyaltytransactions.services import reverse_document
    from apps.stockmovements import sales as stock

    reverse_document(invoice)
    stock.give_back(invoice, "invoice", user)
    return invoice


def refresh_paid(invoice: Invoice) -> Invoice:
    """Recompute what has been paid or credited, and the status that follows from it."""
    from apps.creditnotes.models import CreditNote
    from apps.payments.models import PaymentAllocation

    if invoice.status in (Invoice.Status.DRAFT, Invoice.Status.VOID):
        return invoice
    paid = PaymentAllocation.objects.filter(invoice=invoice, payment__status="posted").aggregate(s=Sum("amount"))["s"] or ZERO
    credited = CreditNote.objects.filter(invoice=invoice, status="issued").aggregate(s=Sum("applied_amount"))["s"] or ZERO
    invoice.amount_paid = paid + credited
    invoice.balance_due = invoice.total - invoice.amount_paid
    if invoice.balance_due <= ZERO:
        invoice.status = Invoice.Status.PAID
    elif invoice.amount_paid > ZERO:
        invoice.status = Invoice.Status.PARTIALLY_PAID
    else:
        invoice.status = Invoice.Status.ISSUED
    invoice.save(update_fields=["amount_paid", "balance_due", "status", "updated_at"])
    return invoice
