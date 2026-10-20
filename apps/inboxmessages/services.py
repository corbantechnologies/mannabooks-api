"""
Sending documents between MannaBooks businesses, and turning what arrives into drafts:
an invoice becomes a bill, a quotation a purchase order, a purchase order an invoice.
The recipient is the active workspace whose KRA PIN is on the customer or supplier.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import InboxMessage

K, S = InboxMessage.Kind, InboxMessage.Status
SENDABLE = {
    # kind: (party attribute, statuses that can't be sent, what the party is called)
    K.INVOICE: ("customer", ("draft", "void"), "customer"),
    K.QUOTATION: ("customer", ("draft", "declined", "converted"), "customer"),
    K.PURCHASE_ORDER: ("supplier", ("draft", "cancelled"), "supplier"),
}


def recipient_for(workspace, kra_pin: str):
    """The other MannaBooks business with this KRA PIN, or None."""
    from apps.workspaces.models import Workspace

    pin = (kra_pin or "").strip().upper()
    if not pin:
        return None
    return Workspace.objects.filter(kra_pin__iexact=pin, is_active=True).exclude(pk=workspace.pk).order_by("created_at").first()


def _document(workspace, kind: str, document_id):
    from apps.invoices.models import Invoice
    from apps.purchaseorders.models import PurchaseOrder
    from apps.quotations.models import Quotation

    model = {K.INVOICE: Invoice, K.QUOTATION: Quotation, K.PURCHASE_ORDER: PurchaseOrder}[kind]
    doc = model.objects.filter(workspace=workspace, pk=document_id).first()
    if doc is None:
        raise BusinessRuleError("That document isn't in this workspace.")
    return doc


def _lines(doc, kind) -> list[dict]:
    rows = []
    for line in doc.lines.select_related("tax_rate"):
        amount = line.total_amount if doc.prices_include_tax else line.net_amount
        rows.append({
            "description": line.description, "quantity": str(line.quantity), "unit": line.unit,
            # what one unit really costs the buyer after any discount, before VAT (or with it, if prices include VAT)
            "unit_price": str((amount / line.quantity).quantize(Decimal("0.0001")) if line.quantity else 0),
            "tax_code": line.tax_rate.code if line.tax_rate_id else "",
            "net": str(line.net_amount), "tax": str(line.tax_amount), "total": str(line.total_amount),
        })
    return rows


def preview(workspace, kind: str, document_id) -> dict:
    """Whether the document's customer or supplier uses MannaBooks, and whether it was sent already."""
    doc = _document(workspace, kind, document_id)
    party = getattr(doc, SENDABLE[kind][0])
    target = recipient_for(workspace, party.kra_pin)
    sent = InboxMessage.objects.filter(sender=workspace, kind=kind, source_id=doc.pk).order_by("-created_at").first()
    return {"available": target is not None, "recipient_name": target.name if target else "", "kra_pin": party.kra_pin,
            "last_status": sent.status if sent else None, "last_sent_at": sent.created_at if sent else None}


@transaction.atomic
def send(workspace, kind: str, document_id, *, message: str = "", user=None) -> InboxMessage:
    attr, blocked, label = SENDABLE[kind]
    doc = _document(workspace, kind, document_id)
    if doc.status in blocked:
        raise BusinessRuleError(f"A {doc.get_status_display().lower()} {K(kind).label.lower()} can't be sent.")
    party = getattr(doc, attr)
    if not party.kra_pin:
        raise BusinessRuleError(f"Add the {label}'s KRA PIN first: that is how MannaBooks finds their business.")
    target = recipient_for(workspace, party.kra_pin)
    if target is None:
        raise BusinessRuleError(f"{party} isn't on MannaBooks yet. Send it by email instead.")
    if InboxMessage.objects.filter(sender=workspace, kind=kind, source_id=doc.pk, status__in=[S.NEW, S.ACCEPTED]).exists():
        raise BusinessRuleError(f"{doc.number} is already in {target.name}'s inbox.")
    if kind == K.INVOICE:
        dates = (doc.issue_date, doc.due_date)
    elif kind == K.QUOTATION:
        dates = (doc.issue_date, doc.valid_until)
    else:
        dates = (doc.order_date, doc.expected_date)
    return InboxMessage.objects.create(
        workspace=target, created_by=user, sender=workspace, sent_by=user, sender_name=workspace.legal_name or workspace.name,
        sender_kra_pin=workspace.kra_pin, kind=kind, source_id=doc.pk, number=doc.number, document_date=dates[0], due_date=dates[1],
        currency=getattr(doc, "currency", workspace.currency) or workspace.currency, prices_include_tax=doc.prices_include_tax,
        subtotal=doc.subtotal, tax_total=doc.tax_total, total=doc.total, lines=_lines(doc, kind), message=message.strip(),
    )


def _supplier(msg: InboxMessage, user):
    """The recipient's supplier record for the sender: matched by KRA PIN, else created from the sender's details."""
    from apps.sequences.services import next_value
    from apps.suppliers.models import Supplier

    found = Supplier.objects.filter(workspace=msg.workspace, kra_pin__iexact=msg.sender_kra_pin).first() if msg.sender_kra_pin else None
    if found:
        return found
    s = msg.sender
    return Supplier.objects.create(workspace=msg.workspace, created_by=user, number=next_value(msg.workspace, "supplier"), name=msg.sender_name,
                                   kra_pin=msg.sender_kra_pin, email=s.email, phone=s.phone, address=s.address)


def _customer(msg: InboxMessage, user):
    from apps.customers.models import Customer
    from apps.sequences.services import next_value

    found = Customer.objects.filter(workspace=msg.workspace, kra_pin__iexact=msg.sender_kra_pin).first() if msg.sender_kra_pin else None
    if found:
        return found
    s = msg.sender
    return Customer.objects.create(workspace=msg.workspace, created_by=user, number=next_value(msg.workspace, "customer"), name=msg.sender_name,
                                   kra_pin=msg.sender_kra_pin, email=s.email, phone=s.phone, address=s.address)


def _rows(msg: InboxMessage, price_key: str, *, account=None) -> tuple[list[dict], bool]:
    """Request rows for the recipient's draft. A business not registered for VAT records the VAT as part of the cost."""
    from apps.taxrates.models import TaxRate

    vat = msg.workspace.vat_registered
    rates = {r.code: r for r in TaxRate.objects.filter(workspace=msg.workspace, kind="vat", is_active=True)}
    rows = []
    for line in msg.lines:
        quantity = Decimal(line["quantity"]) or Decimal(1)
        if vat:
            row = {price_key: Decimal(line["unit_price"]), "tax_rate": rates.get(line["tax_code"])}
        else:
            row = {price_key: (Decimal(line["total"]) / quantity).quantize(Decimal("0.0001")), "tax_rate": None}
        row.update({"description": line["description"][:255], "quantity": quantity})
        if account is not None:
            row["account"] = account
        rows.append(row)
    return rows, msg.prices_include_tax if vat else False


@transaction.atomic
def accept(msg: InboxMessage, *, account=None, user=None) -> InboxMessage:
    """Create the draft on the recipient's side and mark the message accepted. Drafts can be checked before posting."""
    msg = InboxMessage.objects.select_for_update().get(pk=msg.pk)
    if msg.status != S.NEW:
        raise BusinessRuleError(f"This was already {msg.get_status_display().lower()}.")
    ws = msg.workspace
    if msg.kind == K.INVOICE:
        from apps.bills import services as bills

        if account is None:
            raise BusinessRuleError("Choose the expense or asset account to record this bill in.")
        rows, include = _rows(msg, "unit_cost", account=account)
        record = bills.save_draft(ws, header={"supplier": _supplier(msg, user), "supplier_invoice_number": msg.number, "bill_date": msg.document_date,
                                              "due_date": msg.due_date or msg.document_date, "prices_include_tax": include,
                                              "notes": f"Received from {msg.sender_name} through MannaBooks."}, rows=rows, user=user)
        msg.created_type = "bill"
    elif msg.kind == K.QUOTATION:
        from apps.purchaseorders import services as orders

        rows, include = _rows(msg, "unit_cost")
        record = orders.save(ws, header={"supplier": _supplier(msg, user), "order_date": timezone.localdate(), "prices_include_tax": include,
                                         "reference": msg.number, "notes": f"From {msg.sender_name}'s quotation {msg.number}."}, rows=rows, user=user)
        msg.created_type = "purchase_order"
    else:
        from apps.invoices import services as invoices

        rows, include = _rows(msg, "unit_price")
        record = invoices.save_draft(ws, header={"customer": _customer(msg, user), "prices_include_tax": include, "reference": msg.number,
                                                 "notes": f"For {msg.sender_name}'s purchase order {msg.number}."}, rows=rows, user=user)
        msg.created_type = "invoice"
    msg.created_id, msg.status, msg.decided_at = record.pk, S.ACCEPTED, timezone.now()
    msg.read_at = msg.read_at or msg.decided_at
    msg.save(update_fields=["created_type", "created_id", "status", "decided_at", "read_at", "updated_at"])
    return msg


def decline(msg: InboxMessage, reason: str) -> InboxMessage:
    if msg.status != S.NEW:
        raise BusinessRuleError(f"This was already {msg.get_status_display().lower()}.")
    if not reason.strip():
        raise BusinessRuleError("Say why, so the sender knows what to fix.")
    msg.status, msg.decline_reason, msg.decided_at = S.DECLINED, reason.strip()[:255], timezone.now()
    msg.read_at = msg.read_at or msg.decided_at
    msg.save(update_fields=["status", "decline_reason", "decided_at", "read_at", "updated_at"])
    return msg
