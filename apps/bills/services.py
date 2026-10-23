from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core import purchases
from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.sequences.services import next_value
from apps.stockmovements.services import Source, move_in, reverse_source

from .models import Bill, BillLine

SOURCE = {"source": "bill", "source_model": "bills.Bill"}
S = Bill.Status


def _rows_from_receipt(grn) -> list[dict]:
    rows = []
    for line in grn.lines.select_related("product__tax_rate", "order_line__tax_rate"):
        qty = line.quantity - line.billed_quantity
        if qty <= 0:
            continue
        tax_rate = line.order_line.tax_rate if line.order_line_id else line.product.tax_rate
        rows.append({"product": line.product, "description": line.description, "quantity": qty, "unit_cost": line.unit_cost,
                     "unit": line.order_line.unit if line.order_line_id else "", "tax_rate": tax_rate, "extra": {"goods_receipt_line": line, "order_line": line.order_line}})
    if not rows:
        raise BusinessRuleError(f"Everything on {grn.number} is already billed.")
    return rows


def _rows_from_order(order) -> list[dict]:
    if order.goods_receipts.filter(status="posted").exists():
        raise BusinessRuleError(f"Goods were received on {order.number}. Bill the goods received notes instead.")
    rows = []
    for line in order.lines.select_related("product", "tax_rate", "account"):
        qty = line.quantity - line.billed_quantity
        if qty > 0:
            rows.append({"product": line.product, "description": line.description, "quantity": qty, "unit_cost": line.unit_cost,
                         "unit": line.unit, "tax_rate": line.tax_rate, **({"account": line.account} if line.account_id else {}), "extra": {"order_line": line}})
    if not rows:
        raise BusinessRuleError(f"Everything on {order.number} is already billed.")
    return rows


def _rows_from_service_order(order) -> list[dict]:
    return [{"product": line.product, "description": line.description, "quantity": line.quantity, "unit_cost": line.unit_cost,
             "unit": line.unit, "tax_rate": line.tax_rate, "account": line.account} for line in order.lines.select_related("product", "tax_rate", "account")]


@transaction.atomic
def save_draft(workspace, *, header: dict, rows: list[dict] | None, user=None, bill: Bill | None = None) -> Bill:
    if bill is not None and bill.status != S.DRAFT:
        raise BusinessRuleError("Only a draft bill can be changed. Void it and enter it again.")
    grn, order, service = header.get("goods_receipt"), header.get("purchase_order"), header.get("service_order")
    supplier = header.get("supplier") or getattr(grn, "supplier", None) or getattr(order, "supplier", None) or getattr(service, "supplier", None)
    if bill is None:
        if supplier is None:
            raise BusinessRuleError("Choose a supplier.")
        bill_date = header.get("bill_date") or timezone.localdate()
        bill = Bill(workspace=workspace, created_by=user, supplier=supplier, bill_date=bill_date,
                    due_date=header.get("due_date") or bill_date + timedelta(days=supplier.payment_terms_days),
                    supplier_invoice_number=header.get("supplier_invoice_number", ""))
        if not rows:
            if grn is not None:
                header.setdefault("purchase_order", grn.purchase_order)
                header.setdefault("warehouse", grn.warehouse)
                rows = _rows_from_receipt(grn)
            elif order is not None:
                rows = _rows_from_order(order)
                header.setdefault("warehouse", order.warehouse)
            elif service is not None:
                rows = _rows_from_service_order(service)
        origin = order or service or header.get("purchase_order")
        if origin is not None:
            header.setdefault("cost_center", origin.cost_center)
            header.setdefault("project", origin.project)
    for key, value in header.items():
        setattr(bill, key, value)
    for doc in (grn, order, service):
        if doc is not None and doc.supplier_id != bill.supplier_id:
            raise BusinessRuleError(f"{doc} belongs to another supplier.")
    if bill.due_date < bill.bill_date:
        raise BusinessRuleError("The due date can't be before the bill date.")
    bill.save()
    if rows is not None:
        for row in rows:  # delivered goods are charged to Goods received not invoiced
            grn_line = (row.get("extra") or {}).get("goods_receipt_line")
            if grn_line is not None and grn_line.stocked:
                row["account"] = system_account(workspace, "grni")
        purchases.write_lines(bill, BillLine, "bill", purchases.resolve_lines(workspace, rows))
    bill.balance_due = bill.total
    bill.save(update_fields=["balance_due", "updated_at"])
    return bill


@transaction.atomic
def bring_in_open(workspace, *, supplier, supplier_invoice_number: str, bill_date, due_date, amount, user=None) -> Bill:
    """
    A supplier invoice still unpaid in the previous system: owed to the supplier and posted against opening balance
    equity (its cost and VAT were recorded before MannaBooks). The supplier's invoice number is kept for paying it.
    """
    from apps.invoices.services import opening_entry_date

    number = supplier_invoice_number.strip()
    if Bill.objects.filter(supplier=supplier, supplier_invoice_number__iexact=number).exclude(status__in=[S.DRAFT, S.VOID]).exists():
        raise BusinessRuleError(f"Invoice {number} from {supplier} is already recorded.")
    label = f"Unpaid bill {number} from {supplier} brought in"
    bill = Bill(workspace=workspace, created_by=user, supplier=supplier, bill_date=bill_date, due_date=due_date, supplier_invoice_number=number)
    bill.save()
    rows = [{"description": f"Unpaid bill {number} brought in from the previous system", "quantity": 1, "unit_cost": amount, "tax_rate": None,
             "account": system_account(workspace, "cogs")}]  # shown on the bill only; the posting below is what counts
    purchases.write_lines(bill, BillLine, "bill", purchases.resolve_lines(workspace, rows))
    bill.number = next_value(workspace, "bill")
    bill.status, bill.amount_paid, bill.balance_due = S.POSTED, ZERO, bill.total
    bill.save()
    replace_for_source(workspace, **SOURCE, source_id=str(bill.pk), entry_date=opening_entry_date(workspace, bill_date), reference=bill.number,
                       description=label, user=user,
                       lines=[LineInput(account=system_account(workspace, "opening_balance_equity"), debit=bill.total, description=label),
                              LineInput(account=system_account(workspace, "payable"), credit=bill.total, description=label)])
    return bill


@transaction.atomic
def post(bill: Bill, user=None) -> Bill:
    from apps.warehouses.services import default_warehouse

    bill = Bill.objects.select_for_update().get(pk=bill.pk)
    if bill.status != S.DRAFT:
        raise BusinessRuleError("This bill is already posted.")
    if not bill.supplier_invoice_number.strip():
        raise BusinessRuleError("Enter the supplier's invoice number.")
    if Bill.objects.filter(supplier=bill.supplier, supplier_invoice_number__iexact=bill.supplier_invoice_number.strip()).exclude(
            status__in=[S.DRAFT, S.VOID]).exclude(pk=bill.pk).exists():
        raise BusinessRuleError(f"Invoice {bill.supplier_invoice_number} from {bill.supplier} is already recorded.")
    lines = list(bill.lines.select_related("product", "account", "tax_rate__purchases_account", "goods_receipt_line", "order_line"))
    if not lines or bill.total <= 0:
        raise BusinessRuleError("Add at least one line with a value.")
    workspace, label = bill.workspace, f"Bill {bill.supplier_invoice_number} from {bill.supplier}"
    bill.number = bill.number or next_value(workspace, "bill")
    source, debits, warehouse = Source("bill", bill.pk, bill.number), {}, None

    def debit(account, amount):
        if amount:
            debits[account] = debits.get(account, ZERO) + amount

    for line in lines:
        grn_line = line.goods_receipt_line
        if grn_line is not None:
            from apps.goodsreceipts.models import GoodsReceiptLine

            grn_line = GoodsReceiptLine.objects.select_for_update().get(pk=grn_line.pk)
            if line.quantity > grn_line.quantity - grn_line.billed_quantity:
                raise BusinessRuleError(f"{line.description}: more billed than was received.")
            grn_line.billed_quantity += line.quantity
            grn_line.save(update_fields=["billed_quantity", "updated_at"])
            if grn_line.stocked:  # clear the accrual at the delivery's value; any price difference goes to cost of sales
                accrued = q2(line.quantity * grn_line.unit_cost)
                debit(system_account(workspace, "grni"), accrued)
                debit(system_account(workspace, "cogs"), line.net_amount - accrued)
            else:
                debit(system_account(workspace, "cogs"), line.net_amount)
        elif line.product is not None and line.product.track_inventory:
            warehouse = warehouse or bill.warehouse or default_warehouse(workspace)
            move_in(product=line.product, warehouse=warehouse, quantity=line.stock_quantity, unit_cost=purchases.net_stock_cost(line),
                    kind="purchase", source=source, date=bill.bill_date)
            debit(system_account(workspace, "inventory"), line.net_amount)
        else:
            debit(line.account, line.net_amount)
        if line.order_line_id:
            ol = line.order_line
            ol.billed_quantity += line.quantity
            if grn_line is None and line.product is not None and line.product.track_inventory:
                ol.received_quantity += line.quantity
            ol.save(update_fields=["billed_quantity", "received_quantity", "updated_at"])
        if line.tax_amount:
            if line.tax_rate is None or line.tax_rate.purchases_account is None:
                raise BusinessRuleError(f"{line.tax_rate} has no account for VAT on purchases. Set it in Tax rates.")
            debit(line.tax_rate.purchases_account, line.tax_amount)
    journal = []
    for account, amount in debits.items():
        if amount > 0:
            journal.append(LineInput(account=account, debit=amount, description=label))
        elif amount < 0:
            journal.append(LineInput(account=account, credit=-amount, description=label))
    journal.append(LineInput(account=system_account(workspace, "payable"), credit=bill.total, description=label))
    replace_for_source(workspace, **SOURCE, source_id=str(bill.pk), entry_date=bill.bill_date, reference=bill.number,
                       description=label, lines=journal, user=user)
    bill.status, bill.amount_paid, bill.balance_due = S.POSTED, ZERO, bill.total
    bill.save()
    if bill.purchase_order_id:
        from apps.purchaseorders.services import refresh_received

        refresh_received(bill.purchase_order)
    return bill


@transaction.atomic
def void(bill: Bill, reason: str, user=None) -> Bill:
    if bill.status == S.VOID:
        raise BusinessRuleError("This bill is already void.")
    if bill.status == S.DRAFT:
        raise BusinessRuleError("Delete a draft instead of voiding it.")
    if bill.amount_paid > 0:
        raise BusinessRuleError("Payments are applied to this bill. Void them first.")
    reverse_source("bill", bill.pk, bill.bill_date)
    replace_for_source(bill.workspace, **SOURCE, source_id=str(bill.pk), entry_date=bill.bill_date, description="", lines=[], user=user)
    for line in bill.lines.select_related("goods_receipt_line", "order_line", "product"):
        if line.goods_receipt_line_id:
            g = line.goods_receipt_line
            g.billed_quantity -= line.quantity
            g.save(update_fields=["billed_quantity", "updated_at"])
        if line.order_line_id:
            ol = line.order_line
            ol.billed_quantity -= line.quantity
            if not line.goods_receipt_line_id and line.product is not None and line.product.track_inventory:
                ol.received_quantity -= line.quantity
            ol.save(update_fields=["billed_quantity", "received_quantity", "updated_at"])
    bill.status, bill.void_reason, bill.balance_due = S.VOID, reason[:255], ZERO
    bill.save(update_fields=["status", "void_reason", "balance_due", "updated_at"])
    if bill.purchase_order_id:
        from apps.purchaseorders.services import refresh_received

        refresh_received(bill.purchase_order)
    return bill


def refresh_paid(bill: Bill) -> Bill:
    from apps.supplierpayments.models import SupplierPaymentAllocation

    if bill.status in (S.DRAFT, S.VOID):
        return bill
    paid = SupplierPaymentAllocation.objects.filter(bill=bill, payment__status="posted").aggregate(s=Sum("amount"))["s"] or ZERO
    bill.amount_paid, bill.balance_due = paid, bill.total - paid
    bill.status = S.PAID if bill.balance_due <= 0 else S.PARTIALLY_PAID if paid > 0 else S.POSTED
    bill.save(update_fields=["amount_paid", "balance_due", "status", "updated_at"])
    return bill
