from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core import sales
from apps.core.exceptions import BusinessRuleError
from apps.core.sales_views import check_customer, default_currency
from apps.sequences.services import next_value

from .models import Quotation, QuotationLine

EDITABLE = (Quotation.Status.DRAFT, Quotation.Status.SENT)
VALID_DAYS = 30
TRANSITIONS = {
    "send": ((Quotation.Status.DRAFT,), Quotation.Status.SENT),
    "accept": ((Quotation.Status.DRAFT, Quotation.Status.SENT), Quotation.Status.ACCEPTED),
    "decline": ((Quotation.Status.DRAFT, Quotation.Status.SENT), Quotation.Status.DECLINED),
    "reopen": ((Quotation.Status.DECLINED, Quotation.Status.ACCEPTED), Quotation.Status.SENT),
}


@transaction.atomic
def save(workspace, *, header: dict, rows: list[dict] | None, user=None, quotation: Quotation | None = None) -> Quotation:
    if quotation is not None and quotation.status not in EDITABLE:
        raise BusinessRuleError("Only draft or sent quotations can be edited.")
    customer = header.get("customer", quotation.customer if quotation else None)
    if customer is None:
        raise BusinessRuleError("Choose a customer.")
    check_customer(customer)
    if quotation is None:
        issue_date = header.get("issue_date") or timezone.localdate()
        quotation = Quotation(
            workspace=workspace, created_by=user, customer=customer, issue_date=issue_date,
            number=next_value(workspace, "quotation"),
            currency=header.get("currency") or default_currency(workspace, customer),
            valid_until=header.get("valid_until") or issue_date + timedelta(days=VALID_DAYS),
        )
    for key, value in header.items():
        setattr(quotation, key, value)
    if quotation.valid_until < quotation.issue_date:
        raise BusinessRuleError("The quotation can't expire before its date.")
    quotation.save()
    if rows is not None:
        sales.write_lines(quotation, QuotationLine, "quotation", sales.resolve_lines(workspace, rows, customer=quotation.customer))
    return quotation


def change_status(quotation: Quotation, action: str) -> Quotation:
    sources, target = TRANSITIONS[action]
    if quotation.status not in sources:
        raise BusinessRuleError(f"A {quotation.get_status_display().lower()} quotation can't be marked {target.label.lower()}.")
    quotation.status = target
    quotation.save(update_fields=["status", "updated_at"])
    return quotation


@transaction.atomic
def convert(quotation: Quotation, user=None):
    """A draft invoice with the quotation's customer and lines."""
    from apps.invoices.services import save_draft

    if quotation.status == Quotation.Status.CONVERTED:
        raise BusinessRuleError("This quotation is already converted.")
    if quotation.status == Quotation.Status.DECLINED:
        raise BusinessRuleError("This quotation was declined.")
    rows = [
        {"product": line.product, "description": line.description, "quantity": line.quantity, "unit_price": line.unit_price,
         "discount_percent": line.discount_percent, "discount_amount": line.discount_amount, "tax_rate": line.tax_rate, "account": line.account}
        for line in quotation.lines.select_related("product", "tax_rate", "account")
    ]
    invoice = save_draft(
        quotation.workspace,
        header={"customer": quotation.customer, "currency": quotation.currency, "prices_include_tax": quotation.prices_include_tax,
                "reference": quotation.reference, "notes": quotation.notes, "quotation": quotation,
                "cost_center": quotation.cost_center, "project": quotation.project},
        rows=rows, user=user,
    )
    quotation.status = Quotation.Status.CONVERTED
    quotation.save(update_fields=["status", "updated_at"])
    return invoice
