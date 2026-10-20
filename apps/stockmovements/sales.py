"""Stock and cost of sales for sales documents: invoices, cash sales and credit notes."""
from django.db import transaction

from apps.core.money import ZERO
from apps.journals.services import LineInput, dimensions_of, replace_for_source
from apps.ledgeraccounts.services import system_account

from .services import Source, move_in, move_out, reverse_source


def _post_cogs(document, doc_type: str, value, *, returned=False, user=None):
    workspace = document.workspace
    lines = []
    if value:
        cogs, inventory = system_account(workspace, "cogs"), system_account(workspace, "inventory")
        label = f"Cost of {document.number}"
        lines = ([LineInput(account=inventory, debit=value, description=label), LineInput(account=cogs, credit=value, description=label)]
                 if returned else
                 [LineInput(account=cogs, debit=value, description=label), LineInput(account=inventory, credit=value, description=label)])
    replace_for_source(workspace, source=f"{doc_type}_cost", source_model=f"stock.{doc_type}", source_id=str(document.pk),
                       entry_date=document.issue_date, description=f"Cost of sales for {document.number}", reference=document.number,
                       lines=lines, user=user, dimensions=dimensions_of(document))


@transaction.atomic
def issue(document, doc_type: str, user=None) -> None:
    """Take a sale's stock items (and the ingredients of made-to-order items) out of the branch's warehouse and post their cost."""
    from apps.billsofmaterials.services import ingredients_for
    from apps.warehouses.services import default_warehouse

    lines = [line for line in document.lines.select_related("product") if line.product]
    tracked = [line for line in lines if line.product.track_inventory]
    made = [line for line in lines if line.product.made_to_order and not line.product.track_inventory]
    if not tracked and not made:
        return
    warehouse = default_warehouse(document.workspace, document.branch)
    source, total = Source(doc_type, document.pk, document.number), ZERO
    takes = [(line.product, line.stock_quantity) for line in tracked]
    for line in made:  # made when sold: the recipe's ingredients leave stock instead
        takes += [(item, qty) for item, qty in ingredients_for(line.product, line.stock_quantity) if qty > 0]
    for product, quantity in takes:
        total += -move_out(product=product, warehouse=warehouse, quantity=quantity, kind="sale", source=source,
                           date=document.issue_date).value
    _post_cogs(document, doc_type, total, user=user)


@transaction.atomic
def give_back(document, doc_type: str, user=None) -> None:
    """A voided sale: its stock comes back and its cost of sales is removed."""
    reverse_source(doc_type, document.pk, document.issue_date)
    _post_cogs(document, doc_type, ZERO, user=user)


@transaction.atomic
def take_back(note, user=None) -> None:
    """A credit note: returned stock items come back in at their current average cost."""
    from apps.warehouses.services import default_warehouse

    tracked = [line for line in note.lines.select_related("product") if line.product and line.product.track_inventory]
    if not tracked:
        return
    warehouse = default_warehouse(note.workspace, note.branch)
    source, total = Source("credit_note", note.pk, note.number), ZERO
    for line in tracked:
        from .models import StockLevel

        level = StockLevel.objects.filter(product=line.product, warehouse=warehouse).first()
        cost = level.average_cost if level and level.average_cost else line.product.cost_price
        total += move_in(product=line.product, warehouse=warehouse, quantity=line.stock_quantity, unit_cost=cost, kind="sale_return",
                         source=source, date=note.issue_date).value
    _post_cogs(note, "credit_note", total, returned=True, user=user)
