from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.sequences.services import next_value

from .models import DeliveryNote, DeliveryNoteLine

TRANSITIONS = {
    "dispatch": ((DeliveryNote.Status.DRAFT,), DeliveryNote.Status.DISPATCHED),
    "deliver": ((DeliveryNote.Status.DRAFT, DeliveryNote.Status.DISPATCHED), DeliveryNote.Status.DELIVERED),
    "void": ((DeliveryNote.Status.DRAFT, DeliveryNote.Status.DISPATCHED), DeliveryNote.Status.VOID),
}


def _write_lines(note, rows):
    if not rows:
        raise BusinessRuleError("Add at least one line.")
    note.lines.all().delete()
    objs = []
    for n, row in enumerate(rows, start=1):
        product = row.get("product")
        description = (row.get("description") or (product.name if product else "")).strip()
        if not description:
            raise BusinessRuleError(f"Line {n}: add a description.")
        if row["quantity"] <= 0:
            raise BusinessRuleError(f"Line {n}: the quantity must be more than zero.")
        objs.append(DeliveryNoteLine(delivery_note=note, product=product, description=description[:255], quantity=row["quantity"],
                                     unit=row.get("unit") or (product.unit if product else ""), line_no=n))
    DeliveryNoteLine.objects.bulk_create(objs)


@transaction.atomic
def save(workspace, *, data: dict, rows: list[dict] | None, user=None, note: DeliveryNote | None = None) -> DeliveryNote:
    if note is not None and note.status != DeliveryNote.Status.DRAFT:
        raise BusinessRuleError("Only a draft delivery note can be edited.")
    invoice = data.get("invoice", note.invoice if note else None)
    customer = data.get("customer") or (invoice.customer if invoice else None) or (note.customer if note else None)
    if customer is None:
        raise BusinessRuleError("Choose a customer or the invoice being delivered.")
    if invoice is not None and invoice.customer_id != customer.id:
        raise BusinessRuleError("That invoice belongs to another customer.")
    if note is None:
        note = DeliveryNote(workspace=workspace, created_by=user, number=next_value(workspace, "delivery_note"), customer=customer,
                            delivery_date=data.get("delivery_date") or timezone.localdate(),
                            delivery_address=customer.address)
        if not rows and invoice is not None:  # deliver everything on the invoice
            rows = [{"product": line.product, "description": line.description, "quantity": line.quantity,
                     "unit": line.product.unit if line.product else ""} for line in invoice.lines.select_related("product")]
    for key, value in data.items():
        setattr(note, key, value)
    note.customer = customer
    note.save()
    if rows is not None:
        _write_lines(note, rows)
    return note


@transaction.atomic
def change_status(note: DeliveryNote, action: str, received_by: str = "") -> DeliveryNote:
    sources, target = TRANSITIONS[action]
    if note.status not in sources:
        raise BusinessRuleError(f"A {note.get_status_display().lower()} delivery note can't be marked {target.label.lower()}.")
    note.status = target
    now = timezone.now()
    if target == DeliveryNote.Status.DISPATCHED:
        note.dispatched_at = now
    if target == DeliveryNote.Status.DELIVERED:
        note.delivered_at = now
        note.dispatched_at = note.dispatched_at or now
        note.received_by = received_by.strip()[:120]
    note.save()
    return note
