from django.db import transaction

from apps.core import sales
from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.core.sales_views import check_customer, default_currency
from apps.invoices.models import Invoice
from apps.invoices.services import refresh_paid
from apps.journals.services import replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.sequences.services import next_value

from .models import CreditNote, CreditNoteLine

SOURCE = {"source": "credit_note", "source_model": "creditnotes.CreditNote"}


@transaction.atomic
def create(workspace, *, header: dict, rows: list[dict], reason: str, invoice: Invoice | None = None, return_stock: bool = True,
           user=None) -> CreditNote:
    customer = header.get("customer") or (invoice.customer if invoice else None)
    if customer is None:
        raise BusinessRuleError("Choose a customer or the invoice being credited.")
    check_customer(customer)
    if invoice is not None:
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.customer_id != customer.id:
            raise BusinessRuleError("That invoice belongs to another customer.")
        if invoice.status in (Invoice.Status.DRAFT, Invoice.Status.VOID):
            raise BusinessRuleError("Only an issued invoice can be credited.")
        header.setdefault("currency", invoice.currency)
        header.setdefault("prices_include_tax", invoice.prices_include_tax)
        header.setdefault("cost_center", invoice.cost_center)
        header.setdefault("project", invoice.project)
        if not rows:  # credit the whole invoice
            rows = [
                {"product": line.product, "description": line.description, "quantity": line.quantity, "unit_price": line.unit_price,
                 "discount_percent": line.discount_percent, "discount_amount": line.discount_amount, "tax_rate": line.tax_rate, "account": line.account}
                for line in invoice.lines.select_related("tax_rate", "account", "product")
            ]
    note = CreditNote(
        workspace=workspace, created_by=user, customer=customer, invoice=invoice, reason=reason.strip()[:255], return_stock=return_stock,
        currency=header.get("currency") or default_currency(workspace, customer),
        **{k: v for k, v in header.items() if k not in ("customer", "currency")},
    )
    note.exchange_rate = sales.document_rate(workspace, note.currency, note.issue_date)
    note.number = next_value(workspace, "credit_note")
    note.save()
    sales.write_lines(note, CreditNoteLine, "credit_note", sales.resolve_lines(workspace, rows, customer=customer))
    if note.total <= ZERO:
        raise BusinessRuleError("A credit note needs at least one line with a value.")
    if invoice is not None and invoice.currency != note.currency:
        raise BusinessRuleError("A credit note must be in the same currency as its invoice.")
    if invoice is not None and note.total > invoice.total:
        raise BusinessRuleError(f"The credit ({note.total:,.2f}) is more than the invoice ({invoice.total:,.2f}).")
    applied = min(note.total, invoice.balance_due) if invoice is not None else ZERO
    note.applied_amount, note.unapplied_amount = applied, note.total - applied
    note.save(update_fields=["applied_amount", "unapplied_amount", "updated_at"])
    lines = list(note.lines.select_related("account", "tax_rate__sales_account"))
    replace_for_source(
        workspace, **SOURCE, source_id=str(note.pk), entry_date=note.issue_date, reference=note.number,
        description=f"Credit note {note.number} to {customer}",
        lines=sales.posting_lines(note, lines, system_account(workspace, "receivable"), label=f"Credit note {note.number}", credit_income=False),
        user=user,
    )
    if invoice is not None:
        refresh_paid(invoice)
    from apps.etimssubmissions.services import request_signing

    request_signing(note, "credit_note")
    if note.return_stock:
        from apps.stockmovements import sales as stock

        stock.take_back(note, user)
    return note


@transaction.atomic
def void(note: CreditNote, reason: str, user=None) -> CreditNote:
    if note.status == CreditNote.Status.VOID:
        raise BusinessRuleError("This credit note is already void.")
    if note.etims_status == "signed":
        raise BusinessRuleError("KRA has signed this credit note; it can't be voided.")
    replace_for_source(note.workspace, **SOURCE, source_id=str(note.pk), entry_date=note.issue_date, description="", lines=[], user=user)
    note.status, note.void_reason, note.applied_amount, note.unapplied_amount = CreditNote.Status.VOID, reason[:255], ZERO, ZERO
    note.save(update_fields=["status", "void_reason", "applied_amount", "unapplied_amount", "updated_at"])
    if note.invoice_id:
        refresh_paid(note.invoice)
    from apps.stockmovements import sales as stock

    stock.give_back(note, "credit_note", user)
    return note
