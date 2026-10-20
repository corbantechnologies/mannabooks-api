"""The documents that can be emailed, and how to read each one: its rows (item, quantity, amount) and its total."""
from collections.abc import Callable
from dataclasses import dataclass

from django.apps import apps


@dataclass(frozen=True)
class Doc:
    title: Callable  # (document) -> "Invoice"
    model: str
    view_perm: str
    send_perm: str
    party: Callable  # (document) -> customer or supplier, or None
    date: Callable
    rows: Callable  # (document) -> [(description, quantity text or "", amount or None)]
    total: Callable  # (document) -> Decimal or None (a delivery note has no money)
    customer_facing: bool = True

    def get(self, workspace, pk):
        return apps.get_model(self.model).objects.filter(workspace=workspace, pk=pk).first()


def _qty(q) -> str:
    return f"{q.normalize():f}"


def _line_qty(line) -> str:
    """ "2 ctn" when the line is in another unit than the product's own, else just the number."""
    if line.unit and getattr(line, "unit_factor", 1) != 1:
        return f"{_qty(line.quantity)} {line.unit}"
    return _qty(line.quantity)


def _line_rows(doc):
    return [(line.description, _line_qty(line), line.total_amount) for line in doc.lines.all()]


def _payment_rows(doc):
    rows = [(f"Invoice {a.invoice.number}", "", a.amount) for a in doc.allocations.select_related("invoice")]
    if doc.unallocated_amount:
        rows.append(("Kept as credit on your account", "", doc.unallocated_amount))
    return rows


def _remittance_rows(doc):
    rows = [(f"Your invoice {a.bill.supplier_invoice_number or a.bill.number}", "", a.amount) for a in doc.allocations.select_related("bill")]
    if doc.withholding_amount:
        rows.append(("Less withholding tax paid to KRA on your behalf", "", -doc.withholding_amount))
    return rows


def _invoice_title(d):
    if d.kind == "debit_note":
        return "Debit note"
    return "Tax invoice" if d.workspace.vat_registered else "Invoice"


DOCS = {
    "invoice": Doc(_invoice_title, "invoices.Invoice", "invoices.view", "invoices.create", lambda d: d.customer, lambda d: d.issue_date,
                   _line_rows, lambda d: d.total),
    "quotation": Doc(lambda d: "Quotation", "quotations.Quotation", "quotations.view", "quotations.manage", lambda d: d.customer,
                     lambda d: d.issue_date, _line_rows, lambda d: d.total),
    "credit_note": Doc(lambda d: "Credit note", "creditnotes.CreditNote", "creditnotes.view", "creditnotes.create", lambda d: d.customer,
                       lambda d: d.issue_date, _line_rows, lambda d: d.total),
    "cash_sale": Doc(lambda d: "Receipt", "receipts.Receipt", "receipts.view", "receipts.create", lambda d: d.customer, lambda d: d.issue_date,
                     _line_rows, lambda d: d.total),
    "payment": Doc(lambda d: "Payment receipt", "payments.Payment", "payments.view", "payments.create", lambda d: d.customer,
                   lambda d: d.payment_date, _payment_rows, lambda d: d.amount),
    "delivery_note": Doc(lambda d: "Delivery note", "deliverynotes.DeliveryNote", "deliverynotes.view", "deliverynotes.manage", lambda d: d.customer,
                         lambda d: d.delivery_date, lambda d: [(line.description, f"{_qty(line.quantity)} {line.unit}".strip(), None) for line in d.lines.all()],
                         lambda d: None),
    "purchase_order": Doc(lambda d: "Purchase order (LPO)", "purchaseorders.PurchaseOrder", "purchaseorders.view", "purchaseorders.create",
                          lambda d: d.supplier, lambda d: d.order_date, _line_rows, lambda d: d.total, customer_facing=False),
    "service_order": Doc(lambda d: "Service order", "serviceorders.ServiceOrder", "purchaseorders.view", "purchaseorders.create",
                         lambda d: d.supplier, lambda d: d.order_date, _line_rows, lambda d: d.total, customer_facing=False),
    "supplier_payment": Doc(lambda d: "Remittance advice", "supplierpayments.SupplierPayment", "supplierpayments.view", "supplierpayments.create",
                            lambda d: d.supplier, lambda d: d.payment_date, _remittance_rows, lambda d: d.amount, customer_facing=False),
}
