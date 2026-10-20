"""The documents that can be emailed, and how to read each one."""
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
    customer_facing: bool = True

    def get(self, workspace, pk):
        return apps.get_model(self.model).objects.filter(workspace=workspace, pk=pk).first()


DOCS = {
    "invoice": Doc(lambda d: "Debit note" if d.kind == "debit_note" else ("Tax invoice" if d.workspace.vat_registered else "Invoice"),
                   "invoices.Invoice", "invoices.view", "invoices.create", lambda d: d.customer, lambda d: d.issue_date),
    "quotation": Doc(lambda d: "Quotation", "quotations.Quotation", "quotations.view", "quotations.manage", lambda d: d.customer, lambda d: d.issue_date),
    "credit_note": Doc(lambda d: "Credit note", "creditnotes.CreditNote", "creditnotes.view", "creditnotes.create", lambda d: d.customer, lambda d: d.issue_date),
    "cash_sale": Doc(lambda d: "Receipt", "receipts.Receipt", "receipts.view", "receipts.create", lambda d: d.customer, lambda d: d.issue_date),
    "purchase_order": Doc(lambda d: "Purchase order (LPO)", "purchaseorders.PurchaseOrder", "purchaseorders.view", "purchaseorders.create",
                          lambda d: d.supplier, lambda d: d.order_date, customer_facing=False),
}
