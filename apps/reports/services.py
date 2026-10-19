from django.db.models import Q, Sum

from apps.core.money import ZERO
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


def _pl_totals(workspace, from_date, to_date, *, cost_center=None, project=None, branch=None) -> dict:
    f = Q(entry__workspace=workspace) & ~Q(entry__status="draft") & Q(entry__entry_date__gte=from_date, entry__entry_date__lte=to_date)
    f &= Q(account__account_type__in=["income", "expense"])
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
