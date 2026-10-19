"""Job costing: a project's income and costs come from the ledger lines tagged with it."""
from django.db.models import Sum

from apps.core.money import ZERO, q2
from apps.journals.models import JournalLine


def summary(project) -> dict:
    lines = JournalLine.objects.filter(project=project, entry__workspace=project.workspace).exclude(entry__status="draft")
    by_account = (lines.values("account_id", "account__code", "account__name", "account__account_type", "account__subtype")
                  .annotate(debit=Sum("debit"), credit=Sum("credit")).order_by("account__code"))
    income, costs, rows = ZERO, ZERO, []
    for r in by_account:
        is_income = r["account__account_type"] == "income"
        amount = (r["credit"] - r["debit"]) if is_income else (r["debit"] - r["credit"])
        if amount == ZERO:
            continue
        if is_income:
            income += amount
        else:
            costs += amount
        rows.append({"account_id": r["account_id"], "code": r["account__code"], "name": r["account__name"],
                     "kind": "income" if is_income else "cost", "amount": amount})
    recent = [
        {"date": line.entry.entry_date, "entry_id": line.entry_id, "number": line.entry.number, "description": line.description or line.entry.description,
         "account": line.account.name, "amount": (line.credit - line.debit) if line.account.account_type == "income" else (line.debit - line.credit),
         "kind": "income" if line.account.account_type == "income" else "cost"}
        for line in lines.select_related("entry", "account").order_by("-entry__entry_date", "-entry__created_at")[:100]
    ]
    from apps.invoices.models import Invoice

    invoices = Invoice.objects.filter(project=project).exclude(status__in=["draft", "void"])
    invoiced = sum((i.total * i.exchange_rate for i in invoices), ZERO)
    outstanding = sum((i.balance_due * i.exchange_rate for i in invoices), ZERO)
    profit = income - costs
    return {
        "income": q2(income), "costs": q2(costs), "profit": q2(profit),
        "margin_percent": q2(profit / income * 100) if income else None,
        "budget_used_percent": q2(costs / project.cost_budget * 100) if project.cost_budget else None,
        "budget_left": q2(project.cost_budget - costs) if project.cost_budget else None,
        "invoiced": q2(invoiced), "outstanding": q2(outstanding),
        "contract_left_to_invoice": q2(project.contract_value - invoiced) if project.contract_value else None,
        "by_account": rows, "recent": recent,
    }
