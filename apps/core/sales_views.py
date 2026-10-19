"""Small helpers shared by the sales document views."""
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.currencies.services import base_currency


def header_from(data: dict, workspace) -> dict:
    """The document fields a request may set (lines handled separately)."""
    fields = {k: data[k] for k in ("issue_date", "reference", "notes", "prices_include_tax", "branch", "cost_center", "project") if k in data}
    if "customer" in data:
        fields["customer"] = data["customer"]
    if "currency" in data:
        fields["currency"] = (data["currency"] or "").upper()
    return fields


def default_currency(workspace, customer) -> str:
    return (customer.currency if customer and customer.currency else base_currency(workspace).code)


def check_customer(customer):
    if customer is not None and not customer.is_active:
        raise BusinessRuleError(f"{customer} is inactive. Reactivate them first.")


def today():
    return timezone.localdate()
