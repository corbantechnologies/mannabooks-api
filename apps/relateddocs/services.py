"""
Walks the links between documents, both ways, from any one of them. It owns no tables: the links are the foreign
keys the documents already have (an invoice's quotation, a bill's LPO and goods received, payment allocations...).
"""
from collections import deque

from django.apps import apps

KINDS = {
    # kind: (model, label, web path, date field, amount field, view permission)
    "quotation": ("quotations.Quotation", "Quotation", "/sales/quotations/{id}", "issue_date", "total", "quotations.view"),
    "invoice": ("invoices.Invoice", "Invoice", "/sales/invoices/{id}", "issue_date", "total", "invoices.view"),
    "credit_note": ("creditnotes.CreditNote", "Credit note", "/sales/credit-notes/{id}", "issue_date", "total", "creditnotes.view"),
    "delivery_note": ("deliverynotes.DeliveryNote", "Delivery note", "/sales/delivery-notes/{id}", "delivery_date", None, "deliverynotes.view"),
    "payment": ("payments.Payment", "Payment received", "/sales/payments/{id}", "payment_date", "amount", "payments.view"),
    "purchase_order": ("purchaseorders.PurchaseOrder", "Purchase order", "/purchasing/orders/{id}", "order_date", "total", "purchaseorders.view"),
    "service_order": ("serviceorders.ServiceOrder", "Service order", "/purchasing/service-orders/{id}", "order_date", "total", "purchaseorders.view"),
    "goods_receipt": ("goodsreceipts.GoodsReceipt", "Goods received", "/purchasing/receipts/{id}", "receipt_date", "total_value", "goodsreceipts.view"),
    "bill": ("bills.Bill", "Bill", "/purchasing/bills/{id}", "bill_date", "total", "bills.view"),
    "payment_voucher": ("paymentvouchers.PaymentVoucher", "Payment voucher", "/purchasing/vouchers/{id}", "voucher_date", "total", "paymentvouchers.view"),
    "supplier_payment": ("supplierpayments.SupplierPayment", "Supplier payment", "/purchasing/payments/{id}", "payment_date", "amount", "supplierpayments.view"),
}
MAX_NODES = 60
# Where each document sits in its process: what it came from comes first.
STAGE = {"quotation": 0, "purchase_order": 0, "service_order": 0, "invoice": 1, "goods_receipt": 1, "delivery_note": 2, "bill": 2,
         "credit_note": 3, "payment_voucher": 3, "payment": 4, "supplier_payment": 4}


def _model(kind):
    return apps.get_model(KINDS[kind][0])


def neighbours(kind: str, doc) -> list[tuple[str, object]]:
    """The documents directly linked to `doc`."""
    out = []
    add = lambda k, items: out.extend((k, x) for x in items if x is not None)  # noqa: E731
    if kind == "quotation":
        add("invoice", doc.invoices.all())
    elif kind == "invoice":
        add("quotation", [doc.quotation])
        add("invoice", [doc.original_invoice, *doc.debit_notes.all()])
        add("credit_note", doc.credit_notes.all())
        add("delivery_note", doc.delivery_notes.all())
        add("payment", {a.payment for a in doc.allocations.select_related("payment")})
    elif kind in ("credit_note", "delivery_note"):
        add("invoice", [doc.invoice])
    elif kind == "payment":
        add("invoice", {a.invoice for a in doc.allocations.select_related("invoice")})
    elif kind == "purchase_order":
        add("goods_receipt", doc.goods_receipts.all())
        add("bill", doc.bills.all())
    elif kind == "service_order":
        add("bill", doc.bills.all())
    elif kind == "goods_receipt":
        add("purchase_order", [doc.purchase_order])
        add("bill", doc.bills.all())
    elif kind == "bill":
        add("purchase_order", [doc.purchase_order])
        add("goods_receipt", [doc.goods_receipt])
        add("service_order", [doc.service_order])
        voucher_model = _model("payment_voucher")
        add("payment_voucher", voucher_model.objects.filter(workspace=doc.workspace, lines__bill=doc).distinct())
        add("supplier_payment", {a.payment for a in doc.allocations.select_related("payment")})
    elif kind == "payment_voucher":
        add("bill", {line.bill for line in doc.lines.select_related("bill")})
        add("supplier_payment", [doc.payment])
    elif kind == "supplier_payment":
        add("bill", {a.bill for a in doc.allocations.select_related("bill")})
        add("payment_voucher", _model("payment_voucher").objects.filter(workspace=doc.workspace, payment=doc))
    return out


def chain(workspace, kind: str, object_id, membership) -> list[dict]:
    """Every document connected to this one (including itself), in the order of the process, that the member may see."""
    start = _model(kind).objects.filter(workspace=workspace, pk=object_id).first()
    if start is None:
        return []
    seen, queue, found = {(kind, start.pk)}, deque([(kind, start)]), [(kind, start)]
    while queue and len(found) < MAX_NODES:
        k, doc = queue.popleft()
        for nk, nd in neighbours(k, doc):
            if (nk, nd.pk) not in seen and nd.workspace_id == workspace.id:
                seen.add((nk, nd.pk))
                found.append((nk, nd))
                queue.append((nk, nd))
    rows = []
    for k, doc in found:
        _, label, path, date_field, amount_field, perm = KINDS[k]
        if not membership.has_perm(perm):
            continue
        if k == "invoice" and getattr(doc, "kind", "") == "debit_note":
            label = "Debit note"
        rows.append({
            "kind": k, "label": label, "id": doc.pk, "number": getattr(doc, "number", "") or "Draft",
            "date": getattr(doc, date_field), "status": getattr(doc, "status", ""), "status_label": doc.get_status_display() if hasattr(doc, "get_status_display") else "",
            "amount": getattr(doc, amount_field) if amount_field else None, "path": path.format(id=doc.pk), "current": doc.pk == start.pk and k == kind,
        })
    rows.sort(key=lambda r: (STAGE[r["kind"]], r["date"]))  # the order of the process, then by date
    return rows
