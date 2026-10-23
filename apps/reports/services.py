from django.db.models import Q, Sum

from apps.core.money import ZERO, q2
from apps.journals.models import JournalLine
from apps.ledgeraccounts.models import LedgerAccount


def account_balances(workspace, *, to_date=None, from_date=None) -> dict:
    """{account_id: (debit_total, credit_total)} over posted entries in the date range."""
    filters = Q(entry__workspace=workspace) & ~Q(entry__status="draft")
    if to_date:
        filters &= Q(entry__entry_date__lte=to_date)
    if from_date:
        filters &= Q(entry__entry_date__gte=from_date)
    rows = JournalLine.objects.filter(filters).values("account").annotate(debit=Sum("debit"), credit=Sum("credit"))
    return {r["account"]: (r["debit"] or ZERO, r["credit"] or ZERO) for r in rows}


def trial_balance(workspace, as_of) -> dict:
    """Every account with a balance at `as_of`, shown on its debit or credit side, with totals."""
    totals = account_balances(workspace, to_date=as_of)
    rows, total_debit, total_credit = [], ZERO, ZERO
    for account in LedgerAccount.objects.filter(workspace=workspace, pk__in=totals.keys()).order_by("code"):
        debit, credit = totals[account.pk]
        net = debit - credit
        if net == ZERO:
            continue
        row = {
            "account_id": account.pk, "code": account.code, "name": account.name, "account_type": account.account_type,
            "debit": net if net > 0 else ZERO, "credit": -net if net < 0 else ZERO,
        }
        total_debit += row["debit"]
        total_credit += row["credit"]
        rows.append(row)
    return {"as_of": as_of, "rows": rows, "total_debit": total_debit, "total_credit": total_credit,
            "balanced": total_debit == total_credit}


# ---------------------------------------------------------------- profit and loss
PL_SECTIONS = [
    ("income", "Sales and operating income", "income"),
    ("cost_of_sales", "Cost of sales", "expense"),
    ("expense", "Operating expenses", "expense"),
    ("other_income", "Other income", "income"),
    ("other_expense", "Other expenses", "expense"),
]


def department_lines(department) -> Q:
    """Journal lines of a department: tagged with it, or with one of its cost centres."""
    return Q(department=department) | Q(department__isnull=True, cost_center__department=department)


def _pl_filter(workspace, from_date, to_date, limit_department=None) -> Q:
    f = Q(entry__workspace=workspace) & ~Q(entry__status="draft") & Q(entry__entry_date__gte=from_date, entry__entry_date__lte=to_date)
    f &= Q(account__account_type__in=["income", "expense"])
    if limit_department is not None:
        f &= department_lines(limit_department)
    return f


def _pl_totals(workspace, from_date, to_date, *, cost_center=None, project=None, branch=None, department=None, limit_department=None) -> dict:
    f = _pl_filter(workspace, from_date, to_date, limit_department)
    if department is not None:
        f &= department_lines(department)
    if cost_center is not None:
        f &= Q(cost_center=cost_center)
    if project is not None:
        f &= Q(project=project)
    if branch is not None:
        f &= Q(branch=branch)
    rows = JournalLine.objects.filter(f).values("account").annotate(debit=Sum("debit"), credit=Sum("credit"))
    return {r["account"]: (r["debit"] or ZERO, r["credit"] or ZERO) for r in rows}


def _section_of(account) -> str:
    if account.subtype in ("income", "other_income", "cost_of_sales", "expense", "other_expense"):
        return account.subtype
    return "income" if account.account_type == "income" else "expense"


def profit_and_loss(workspace, *, from_date, to_date, compare_from=None, compare_to=None, **dims) -> dict:
    """`dims`: cost_center, project, branch or department to report on one of them; limit_department for someone limited to one."""
    now = _pl_totals(workspace, from_date, to_date, **dims)
    before = _pl_totals(workspace, compare_from, compare_to, **dims) if compare_from and compare_to else {}
    accounts = LedgerAccount.objects.filter(workspace=workspace, pk__in=set(now) | set(before)).order_by("code")
    sections = {key: {"key": key, "label": label, "rows": [], "total": ZERO, "compare_total": ZERO} for key, label, _ in PL_SECTIONS}
    for account in accounts:
        key = _section_of(account)
        income = account.account_type == "income"

        def signed(pair, income=income):
            debit, credit = pair
            return (credit - debit) if income else (debit - credit)

        amount, compare = signed(now.get(account.pk, (ZERO, ZERO))), signed(before.get(account.pk, (ZERO, ZERO)))
        if amount == ZERO and compare == ZERO:
            continue
        sec = sections[key]
        sec["rows"].append({"account_id": account.pk, "code": account.code, "name": account.name, "amount": amount, "compare": compare})
        sec["total"] += amount
        sec["compare_total"] += compare

    def t(key, field="total"):
        return sections[key][field]

    def results(field):
        gross = t("income", field) - t("cost_of_sales", field)
        operating = gross - t("expense", field)
        return gross, operating, operating + t("other_income", field) - t("other_expense", field)

    gross, operating, net = results("total")
    c_gross, c_operating, c_net = results("compare_total")
    return {
        "from_date": from_date, "to_date": to_date, "compare_from": compare_from, "compare_to": compare_to,
        "sections": [sections[key] for key, _, _ in PL_SECTIONS],
        "gross_profit": gross, "operating_profit": operating, "net_profit": net,
        "compare_gross_profit": c_gross, "compare_operating_profit": c_operating, "compare_net_profit": c_net,
    }


# ---------------------------------------------------------------- P&L side by side
DIMENSIONS = {
    "department": ("departments.Department", "Departments"),
    "cost_center": ("costcenters.CostCenter", "Cost centres"),
    "branch": ("branches.Branch", "Branches"),
    "project": ("projects.Project", "Projects"),
}


def profit_and_loss_by(workspace, *, from_date, to_date, dimension: str, limit_department=None) -> dict:
    """
    Profit and loss with one column per department (or cost centre, branch or project), a column for lines not
    tagged with any, and the total. A line takes its department from its cost centre when it has none of its own.
    """
    from django.apps import apps as django_apps
    from django.db.models import F
    from django.db.models.functions import Coalesce

    key = Coalesce("department", "cost_center__department") if dimension == "department" else F(dimension)
    rows = (JournalLine.objects.filter(_pl_filter(workspace, from_date, to_date, limit_department)).annotate(dim=key)
            .values("account", "dim").annotate(debit=Sum("debit"), credit=Sum("credit")))
    model = django_apps.get_model(DIMENSIONS[dimension][0])
    ids = {r["dim"] for r in rows if r["dim"] is not None}
    items = sorted(model.objects.filter(pk__in=ids), key=lambda x: (getattr(x, "code", "") or "", x.name.lower()))
    columns = [{"id": str(i.pk), "name": f"{i.code} {i.name}".strip() if getattr(i, "code", "") else i.name} for i in items]
    position = {i.pk: n for n, i in enumerate(items)}
    if any(r["dim"] is None for r in rows):
        columns.append({"id": None, "name": "Not tagged"})
    width = len(columns)
    accounts = {a.pk: a for a in LedgerAccount.objects.filter(workspace=workspace, pk__in={r["account"] for r in rows})}
    sections = {k: {"key": k, "label": label, "rows": {}, "totals": [ZERO] * width, "total": ZERO} for k, label, _ in PL_SECTIONS}
    for r in rows:
        account = accounts[r["account"]]
        income = account.account_type == "income"
        amount = ((r["credit"] or ZERO) - (r["debit"] or ZERO)) if income else ((r["debit"] or ZERO) - (r["credit"] or ZERO))
        if amount == ZERO:
            continue
        col = position[r["dim"]] if r["dim"] is not None else width - 1
        sec = sections[_section_of(account)]
        row = sec["rows"].setdefault(account.pk, {"account_id": account.pk, "code": account.code, "name": account.name, "amounts": [ZERO] * width,
                                                  "total": ZERO})
        row["amounts"][col] += amount
        row["total"] += amount
        sec["totals"][col] += amount
        sec["total"] += amount

    def line(key):
        return sections[key]["totals"] + [sections[key]["total"]]

    def combine(*parts):
        return [sum(values) for values in zip(*parts, strict=True)]

    neg = lambda values: [-v for v in values]  # noqa: E731
    gross = combine(line("income"), neg(line("cost_of_sales")))
    operating = combine(gross, neg(line("expense")))
    net = combine(operating, line("other_income"), neg(line("other_expense")))
    return {
        "from_date": from_date, "to_date": to_date, "dimension": dimension, "dimension_label": DIMENSIONS[dimension][1], "columns": columns,
        "sections": [{**sections[k], "rows": sorted(sections[k]["rows"].values(), key=lambda x: x["code"])} for k, _, _ in PL_SECTIONS],
        "gross_profit": gross, "operating_profit": operating, "net_profit": net,
    }


# ---------------------------------------------------------------- balance sheet
BS_GROUPS = [
    ("current_assets", "Current assets", "asset", {"cash", "bank", "receivable", "inventory", "current_asset", "tax_asset"}),
    ("fixed_assets", "Fixed assets", "asset", {"fixed_asset"}),
    ("current_liabilities", "Current liabilities", "liability", {"payable", "tax_liability", "current_liability"}),
    ("long_term_liabilities", "Long-term liabilities", "liability", {"long_term_liability"}),
    ("equity", "Equity", "equity", {"equity"}),
]


def _balances_at(workspace, as_of) -> tuple[dict, object]:
    totals = account_balances(workspace, to_date=as_of)
    accounts = {a.pk: a for a in LedgerAccount.objects.filter(workspace=workspace, pk__in=totals.keys())}
    out, profit = {}, ZERO
    for pk, (debit, credit) in totals.items():
        account = accounts[pk]
        if account.account_type in ("income", "expense"):
            profit += credit - debit  # not yet closed into retained earnings
            continue
        out[pk] = (account, (debit - credit) if account.account_type == "asset" else (credit - debit))
    return out, profit


def balance_sheet(workspace, *, as_of, compare_as_of=None) -> dict:
    now, profit = _balances_at(workspace, as_of)
    before, c_profit = _balances_at(workspace, compare_as_of) if compare_as_of else ({}, ZERO)
    groups = {key: {"key": key, "label": label, "rows": [], "total": ZERO, "compare_total": ZERO} for key, label, _, _ in BS_GROUPS}
    pks = set(now) | set(before)
    for pk in sorted(pks, key=lambda p: (now.get(p) or before.get(p))[0].code):
        account = (now.get(pk) or before.get(pk))[0]
        amount = now[pk][1] if pk in now else ZERO
        compare = before[pk][1] if pk in before else ZERO
        if amount == ZERO and compare == ZERO:
            continue
        key = next((k for k, _, kind, subtypes in BS_GROUPS if kind == account.account_type and account.subtype in subtypes),
                   {"asset": "current_assets", "liability": "current_liabilities"}.get(account.account_type, "equity"))
        g = groups[key]
        g["rows"].append({"account_id": account.pk, "code": account.code, "name": account.name, "amount": amount, "compare": compare})
        g["total"] += amount
        g["compare_total"] += compare
    eq = groups["equity"]
    eq["rows"].append({"account_id": None, "code": "", "name": "Profit for the year (not yet closed)", "amount": profit, "compare": c_profit})
    eq["total"] += profit
    eq["compare_total"] += c_profit

    def sums(field):
        assets = groups["current_assets"][field] + groups["fixed_assets"][field]
        liabilities = groups["current_liabilities"][field] + groups["long_term_liabilities"][field]
        return assets, liabilities, groups["equity"][field]

    assets, liabilities, equity = sums("total")
    c_assets, c_liabilities, c_equity = sums("compare_total")
    return {
        "as_of": as_of, "compare_as_of": compare_as_of, "groups": [groups[k] for k, _, _, _ in BS_GROUPS],
        "total_assets": assets, "total_liabilities": liabilities, "total_equity": equity,
        "compare_total_assets": c_assets, "compare_total_liabilities": c_liabilities, "compare_total_equity": c_equity,
        "balanced": assets == liabilities + equity,
    }


# ---------------------------------------------------------------- ageing
BUCKETS = ["current", "days_1_30", "days_31_60", "days_61_90", "over_90"]


def _bucket(days: int) -> str:
    if days <= 0:
        return "current"
    if days <= 30:
        return "days_1_30"
    if days <= 60:
        return "days_31_60"
    if days <= 90:
        return "days_61_90"
    return "over_90"


def aged(workspace, *, kind: str, as_of) -> dict:
    """Unpaid invoices (receivables) or bills (payables) by how long they are overdue, in the base currency."""
    if kind == "receivables":
        from apps.invoices.models import Invoice

        docs = (Invoice.objects.filter(workspace=workspace, status__in=["issued", "partially_paid"], balance_due__gt=0, issue_date__lte=as_of)
                .select_related("customer"))
        items = [(d.customer, d, d.balance_due * d.exchange_rate) for d in docs]
    else:
        from apps.bills.models import Bill

        docs = Bill.objects.filter(workspace=workspace, status__in=["posted", "partially_paid"], balance_due__gt=0, bill_date__lte=as_of).select_related("supplier")
        items = [(d.supplier, d, d.balance_due) for d in docs]
    parties, totals = {}, {b: ZERO for b in BUCKETS}
    for party, doc, amount in items:
        row = parties.setdefault(party.pk, {"party_id": party.pk, "name": party.name, **{b: ZERO for b in BUCKETS}, "total": ZERO, "documents": []})
        b = _bucket((as_of - doc.due_date).days)
        row[b] += amount
        row["total"] += amount
        totals[b] += amount
        row["documents"].append({"id": doc.pk, "number": doc.number, "due_date": doc.due_date, "days_overdue": max((as_of - doc.due_date).days, 0),
                                 "amount": amount})
    rows = sorted(parties.values(), key=lambda r: -r["total"])
    return {"as_of": as_of, "kind": kind, "rows": rows, "totals": {**totals, "total": sum(totals.values(), ZERO)}}


# ---------------------------------------------------------------- VAT
def vat_summary(workspace, *, from_date, to_date) -> dict:
    """Sales and purchases by VAT rate for a return period, from the documents, in the base currency."""
    from apps.bills.models import BillLine
    from apps.creditnotes.models import CreditNoteLine
    from apps.expenses.models import ExpenseLine
    from apps.invoices.models import InvoiceLine
    from apps.receipts.models import ReceiptLine

    sales, purchases = {}, {}

    def add(book, rate, net, tax, sign=1):
        key = rate.pk if rate else None
        row = book.setdefault(key, {"tax_rate": rate.name if rate else "No VAT", "rate": rate.rate if rate else ZERO, "net": ZERO, "tax": ZERO})
        row["net"] += sign * net
        row["tax"] += sign * tax

    rng = {"gte": from_date, "lte": to_date}
    for line in InvoiceLine.objects.filter(invoice__workspace=workspace, invoice__issue_date__gte=rng["gte"], invoice__issue_date__lte=rng["lte"]
                                           ).exclude(invoice__status__in=["draft", "void"]).select_related("invoice", "tax_rate"):
        add(sales, line.tax_rate, line.net_amount * line.invoice.exchange_rate, line.tax_amount * line.invoice.exchange_rate)
    for line in ReceiptLine.objects.filter(receipt__workspace=workspace, receipt__status="issued", receipt__issue_date__gte=rng["gte"],
                                           receipt__issue_date__lte=rng["lte"]).select_related("receipt", "tax_rate"):
        add(sales, line.tax_rate, line.net_amount * line.receipt.exchange_rate, line.tax_amount * line.receipt.exchange_rate)
    for line in CreditNoteLine.objects.filter(credit_note__workspace=workspace, credit_note__status="issued", credit_note__issue_date__gte=rng["gte"],
                                              credit_note__issue_date__lte=rng["lte"]).select_related("credit_note", "tax_rate"):
        add(sales, line.tax_rate, line.net_amount * line.credit_note.exchange_rate, line.tax_amount * line.credit_note.exchange_rate, -1)
    for line in BillLine.objects.filter(bill__workspace=workspace, bill__bill_date__gte=rng["gte"], bill__bill_date__lte=rng["lte"]
                                        ).exclude(bill__status__in=["draft", "void"]).select_related("tax_rate"):
        add(purchases, line.tax_rate, line.net_amount, line.tax_amount)
    for line in ExpenseLine.objects.filter(expense__workspace=workspace, expense__status="posted", expense__expense_date__gte=rng["gte"],
                                           expense__expense_date__lte=rng["lte"]).select_related("tax_rate"):
        add(purchases, line.tax_rate, line.net_amount, line.tax_amount)

    def finish(book):
        rows = sorted(book.values(), key=lambda r: -r["rate"])
        for r in rows:
            r["net"], r["tax"] = r["net"].quantize(ZERO), r["tax"].quantize(ZERO)
        return rows

    s_rows, p_rows = finish(sales), finish(purchases)
    output_vat, input_vat = sum((r["tax"] for r in s_rows), ZERO), sum((r["tax"] for r in p_rows), ZERO)
    return {"from_date": from_date, "to_date": to_date, "sales": s_rows, "purchases": p_rows, "output_vat": output_vat, "input_vat": input_vat,
            "net_vat": output_vat - input_vat}



# ---------------------------------------------------------------- by category
def by_category(workspace, *, from_date, to_date) -> dict:
    """Per product category: how many products, the stock value now, and net sales (less credit notes) in the period."""
    from collections import defaultdict

    from django.db.models import Count, F

    from apps.creditnotes.models import CreditNoteLine
    from apps.invoices.models import InvoiceLine
    from apps.productcategories.models import ProductCategory
    from apps.products.models import Product
    from apps.receipts.models import ReceiptLine
    from apps.stockmovements.models import StockLevel

    rows = defaultdict(lambda: {"products": 0, "stock_value": ZERO, "sales": ZERO})
    names = {c.pk: c.name for c in ProductCategory.objects.filter(workspace=workspace)}
    for row in Product.objects.filter(workspace=workspace, is_active=True).values("category_id").annotate(n=Count("id")):
        rows[row["category_id"]]["products"] = row["n"]
    for row in StockLevel.objects.filter(workspace=workspace).values("product__category_id").annotate(v=Sum(F("quantity") * F("average_cost"))):
        rows[row["product__category_id"]]["stock_value"] += row["v"] or ZERO
    sources = (
        (InvoiceLine, "invoice", {"invoice__status__in": ["issued", "partially_paid", "paid"]}, 1),
        (ReceiptLine, "receipt", {"receipt__status": "issued"}, 1),
        (CreditNoteLine, "credit_note", {"credit_note__status": "issued"}, -1),
    )
    for model, parent, status, sign in sources:
        lines = model.objects.filter(**{f"{parent}__workspace": workspace, f"{parent}__issue_date__gte": from_date,
                                        f"{parent}__issue_date__lte": to_date}, **status)
        for row in lines.values("product__category_id").annotate(a=Sum(F("net_amount") * F(f"{parent}__exchange_rate"))):
            rows[row["product__category_id"]]["sales"] += sign * (row["a"] or ZERO)
    total_sales = sum((r["sales"] for r in rows.values()), ZERO)
    result = []
    for key, r in rows.items():
        if not (r["products"] or r["stock_value"] or r["sales"]):
            continue
        result.append({"category_id": key, "name": names.get(key, "No category"), "products": r["products"],
                       "stock_value": q2(r["stock_value"]), "sales": q2(r["sales"]),
                       "share": q2(r["sales"] / total_sales * 100) if total_sales else ZERO})
    result.sort(key=lambda r: (-r["sales"], -r["stock_value"]))
    return {"from_date": from_date, "to_date": to_date, "rows": result, "total_sales": q2(total_sales),
            "total_stock_value": q2(sum((r["stock_value"] for r in result), ZERO))}


# ---------------------------------------------------------------- period summary (the dashboard)
def period_summary(workspace, *, from_date, to_date) -> dict:
    """The headline numbers for a month or a year: profit, cash, sales, buying, VAT, payroll, who owes whom, and the top sellers."""
    from collections import defaultdict
    from datetime import timedelta

    from django.db.models import F

    from apps.bills.models import Bill
    from apps.expenses.models import Expense
    from apps.invoices.models import Invoice, InvoiceLine
    from apps.payments.models import Payment
    from apps.payruns.models import PayRun
    from apps.receipts.models import Receipt, ReceiptLine

    pl = profit_and_loss(workspace, from_date=from_date, to_date=to_date)
    sec = {s["key"]: s["total"] for s in pl["sections"]}
    rng = {"gte": from_date, "lte": to_date}

    cash = JournalLine.objects.filter(entry__workspace=workspace, account__subtype__in=["cash", "bank"]).exclude(entry__status="draft")
    period_cash = cash.filter(entry__entry_date__gte=from_date, entry__entry_date__lte=to_date).aggregate(i=Sum("debit"), o=Sum("credit"))
    closing = cash.filter(entry__entry_date__lte=to_date).aggregate(d=Sum("debit"), c=Sum("credit"))

    invoices = Invoice.objects.filter(workspace=workspace, issue_date__gte=rng["gte"], issue_date__lte=rng["lte"]).exclude(status__in=["draft", "void"])
    receipts = Receipt.objects.filter(workspace=workspace, status="issued", issue_date__gte=rng["gte"], issue_date__lte=rng["lte"])
    bills = Bill.objects.filter(workspace=workspace, bill_date__gte=rng["gte"], bill_date__lte=rng["lte"]).exclude(status__in=["draft", "void"])
    expenses = Expense.objects.filter(workspace=workspace, status="posted", expense_date__gte=rng["gte"], expense_date__lte=rng["lte"])
    payments = Payment.objects.filter(workspace=workspace, payment_date__gte=rng["gte"], payment_date__lte=rng["lte"]).exclude(status="void")
    payroll = PayRun.objects.filter(workspace=workspace, pay_date__gte=rng["gte"], pay_date__lte=rng["lte"]).exclude(status="draft")

    def total(qs, field="total", rate=False):
        expr = F(field) * F("exchange_rate") if rate else F(field)
        return qs.aggregate(t=Sum(expr))["t"] or ZERO

    customers = defaultdict(lambda: {"name": "", "amount": ZERO})
    for inv in invoices.select_related("customer"):
        c = customers[inv.customer_id]
        c["name"], c["amount"] = inv.customer.name, c["amount"] + inv.subtotal * inv.exchange_rate
    for r in receipts.select_related("customer"):
        key = r.customer_id or "walk-in"
        c = customers[key]
        c["name"] = r.customer.name if r.customer_id else "Walk-in customers"
        c["amount"] += r.subtotal * r.exchange_rate

    products = defaultdict(lambda: {"name": "", "quantity": ZERO, "amount": ZERO})
    for model, parent in ((InvoiceLine, "invoice"), (ReceiptLine, "receipt")):
        lines = model.objects.filter(**{f"{parent}__in": invoices if parent == "invoice" else receipts})
        for row in lines.values("product_id", "description").annotate(q=Sum(F("quantity") * F("unit_factor")), a=Sum(F("net_amount") * F(f"{parent}__exchange_rate"))):
            key = row["product_id"] or row["description"]
            p = products[key]
            p["name"] = p["name"] or row["description"]
            p["quantity"] += row["q"] or ZERO
            p["amount"] += row["a"] or ZERO

    # month by month inside the range (for a year: twelve bars)
    by_month = []
    cursor = from_date.replace(day=1)
    while cursor <= to_date:
        nxt = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        m_pl = _pl_totals(workspace, max(cursor, from_date), min(nxt - timedelta(days=1), to_date))
        income = expense = ZERO
        accounts = {a.pk: a for a in LedgerAccount.objects.filter(workspace=workspace, pk__in=m_pl.keys())}
        for pk, (debit, credit) in m_pl.items():
            if accounts[pk].account_type == "income":
                income += credit - debit
            else:
                expense += debit - credit
        by_month.append({"month": cursor, "income": income, "expenses": expense, "profit": income - expense})
        cursor = nxt

    vat = vat_summary(workspace, from_date=from_date, to_date=to_date)
    receivable = aged(workspace, kind="receivables", as_of=to_date)["totals"]
    payable = aged(workspace, kind="payables", as_of=to_date)["totals"]
    return {
        "from_date": from_date, "to_date": to_date,
        "income": sec["income"] + sec["other_income"], "cost_of_sales": sec["cost_of_sales"], "expenses": sec["expense"] + sec["other_expense"],
        "gross_profit": pl["gross_profit"], "net_profit": pl["net_profit"],
        "cash_in": period_cash["i"] or ZERO, "cash_out": period_cash["o"] or ZERO,
        "cash_balance": (closing["d"] or ZERO) - (closing["c"] or ZERO),
        "invoiced": total(invoices, rate=True), "invoice_count": invoices.count(),
        "cash_sales": total(receipts, rate=True), "cash_sale_count": receipts.count(),
        "payments_received": payments.aggregate(t=Sum("amount"))["t"] or ZERO,
        "bills": total(bills), "bill_count": bills.count(), "spent_on_expenses": total(expenses),
        "payroll_cost": payroll.aggregate(t=Sum("employer_cost"))["t"] or ZERO,
        "output_vat": vat["output_vat"], "input_vat": vat["input_vat"], "net_vat": vat["net_vat"],
        "receivables": receivable["total"], "receivables_overdue": receivable["total"] - receivable["current"],
        "payables": payable["total"], "payables_overdue": payable["total"] - payable["current"],
        "top_customers": sorted(customers.values(), key=lambda c: -c["amount"])[:5],
        "top_products": sorted(products.values(), key=lambda p: -p["amount"])[:5],
        "by_month": by_month,
    }
