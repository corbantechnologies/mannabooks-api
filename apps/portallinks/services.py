from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import PortalLink


def open_link(token: str) -> PortalLink:
    link = PortalLink.objects.select_related("workspace", "customer", "invoice").filter(token=token).first()
    if link is None or link.revoked_at or (link.expires_at and link.expires_at < timezone.now()) or not link.workspace.is_active:
        raise BusinessRuleError("This link has expired. Ask the business for a new one.")
    return link


def invoice_data(invoice) -> dict:
    return {
        "id": str(invoice.id), "number": invoice.number, "kind": invoice.kind, "issue_date": invoice.issue_date, "due_date": invoice.due_date,
        "status": invoice.status, "currency": invoice.currency, "subtotal": str(invoice.subtotal), "tax_total": str(invoice.tax_total),
        "total": str(invoice.total), "amount_paid": str(invoice.amount_paid), "balance_due": str(invoice.balance_due),
        "etims_cu_invoice_number": invoice.etims_cu_invoice_number, "etims_qr_url": invoice.etims_qr_url,
        "lines": [{"description": ln.description, "quantity": str(ln.quantity), "unit_price": str(ln.unit_price),
                   "tax_rate_name": ln.tax_rate.name if ln.tax_rate else None, "total_amount": str(ln.total_amount)}
                  for ln in invoice.lines.select_related("tax_rate")],
    }


def portal_data(link: PortalLink) -> dict:
    from apps.customers.services import balance_of
    from apps.invoices.models import Invoice
    from apps.mpesaconnections.models import MpesaConnection

    ws = link.workspace
    if link.invoice is not None:
        invoices = [link.invoice]
    else:
        invoices = list(Invoice.objects.filter(customer=link.customer, status__in=["issued", "partially_paid"]).order_by("due_date"))
    return {
        "business": {"name": ws.legal_name or ws.name, "phone": ws.phone, "email": ws.email, "address": ws.address,
                     "kra_pin": ws.kra_pin, "logo_url": ws.logo_url},
        "customer": {"name": link.customer.name, "number": link.customer.number},
        "scope": "invoice" if link.invoice_id else "statement",
        "balance": str(balance_of(link.customer)),
        "invoices": [invoice_data(i) for i in invoices],
        "mpesa_available": MpesaConnection.objects.filter(workspace=ws, is_active=True).exists(),
    }


def invoice_for(link: PortalLink, invoice_id):
    from apps.invoices.models import Invoice

    qs = Invoice.objects.filter(customer=link.customer, status__in=["issued", "partially_paid", "paid"])
    if link.invoice_id:
        qs = qs.filter(pk=link.invoice_id)
    invoice = qs.filter(pk=invoice_id).first()
    if invoice is None:
        raise BusinessRuleError("That invoice is not on this link.")
    return invoice
