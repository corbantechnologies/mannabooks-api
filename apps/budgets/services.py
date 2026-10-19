"""Budgets: save, approve, fill from last year, and compare with the ledger."""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.journals.models import JournalLine

from .models import Budget, BudgetLine

S = Budget.Status


def month_starts(fiscal_year) -> list[date]:
    first = fiscal_year.start_date.replace(day=1)
    out = []
    for i in range(12):
        y, m = divmod(first.month - 1 + i, 12)
        out.append(date(first.year + y, m + 1, 1))
    return out


def _signed(account_type: str, debit, credit):
    return (credit - debit) if account_type == "income" else (debit - credit)


@transaction.atomic
def save(workspace, *, header: dict, lines: list[dict] | None, user=None, budget: Budget | None = None) -> Budget:
    if budget is not None and budget.status != S.DRAFT:
        raise BusinessRuleError("An approved budget can't be changed. Reopen it first.")
    if budget is None:
        budget = Budget(workspace=workspace, created_by=user)
    for key, value in header.items():
        setattr(budget, key, value)
    if budget.fiscal_year_id is None:
        raise BusinessRuleError("Choose the financial year.")
    if Budget.objects.filter(workspace=workspace, fiscal_year=budget.fiscal_year, name__iexact=budget.name).exclude(pk=budget.pk).exists():
        raise BusinessRuleError("This year already has a budget with that name.")
    budget.save()
    if lines is not None:
        write_lines(budget, lines)
    return budget


def write_lines(budget: Budget, lines: list[dict]) -> None:
    seen = set()
    budget.lines.all().delete()
    rows = []
    for n, row in enumerate(lines, start=1):
        account = row["account"]
        if account.account_type not in ("income", "expense"):
            raise BusinessRuleError(f"Line {n}: budgets cover income and expense accounts only ({account} isn't one).")
        if account.pk in seen:
            raise BusinessRuleError(f"Line {n}: {account} is in the budget twice.")
        seen.add(account.pk)
        amounts = [q2(Decimal(str(a or 0))) for a in row["amounts"]]
        if len(amounts) != 12:
            raise BusinessRuleError(f"Line {n}: enter 12 monthly amounts.")
        if any(a < 0 for a in amounts):
            raise BusinessRuleError(f"Line {n}: amounts can't be negative.")
        rows.append(BudgetLine(budget=budget, account=account, amounts=[str(a) for a in amounts], total=sum(amounts, ZERO)))
    BudgetLine.objects.bulk_create(rows)


def approve(budget: Budget, user) -> Budget:
    if budget.status != S.DRAFT:
        raise BusinessRuleError("This budget is already approved.")
    if not budget.lines.exists():
        raise BusinessRuleError("Add at least one account first.")
    clash = Budget.objects.filter(workspace=budget.workspace, fiscal_year=budget.fiscal_year, cost_center=budget.cost_center,
                                  project=budget.project, status=S.APPROVED).exclude(pk=budget.pk).first()
    if clash is not None:
        raise BusinessRuleError(f"{clash.name} is already the approved budget for this year and scope. Reopen it first.")
    from apps.approvalrequests.services import gate

    if not gate("budget", budget, user):
        return budget
    budget.status, budget.approved_by, budget.approved_at = S.APPROVED, user, timezone.now()
    budget.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return budget


def reopen(budget: Budget) -> Budget:
    if budget.status != S.APPROVED:
        raise BusinessRuleError("Only an approved budget can be reopened.")
    budget.status, budget.approved_by, budget.approved_at = S.DRAFT, None, None
    budget.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return budget


def _ledger(workspace, *, start, end, cost_center=None, project=None, accounts=None):
    """{(account_id, month_start): signed amount} for income and expense lines in the range."""
    f = Q(entry__workspace=workspace) & ~Q(entry__status="draft") & Q(entry__entry_date__gte=start, entry__entry_date__lte=end)
    f &= Q(account__account_type__in=["income", "expense"])
    if cost_center is not None:
        f &= Q(cost_center=cost_center)
    if project is not None:
        f &= Q(project=project)
    if accounts is not None:
        f &= Q(account__in=accounts)
    rows = (JournalLine.objects.filter(f).annotate(month=TruncMonth("entry__entry_date"))
            .values("account_id", "account__account_type", "month").annotate(debit=Sum("debit"), credit=Sum("credit")))
    out = {}
    for r in rows:
        month = r["month"].date() if hasattr(r["month"], "date") else r["month"]
        out[(r["account_id"], month)] = _signed(r["account__account_type"], r["debit"], r["credit"])
    return out


@transaction.atomic
def fill_from_last_year(budget: Budget, uplift_percent=ZERO) -> Budget:
    """Replace the lines with last year's actual figures, month by month, plus an uplift."""
    if budget.status != S.DRAFT:
        raise BusinessRuleError("Reopen the budget first.")
    months = month_starts(budget.fiscal_year)
    start = date(months[0].year - 1, months[0].month, 1)
    end = budget.fiscal_year.start_date - timedelta(days=1)
    actual = _ledger(budget.workspace, start=start, end=end, cost_center=budget.cost_center, project=budget.project)
    if not actual:
        raise BusinessRuleError("There are no income or expense figures in the 12 months before this year.")
    factor = 1 + Decimal(str(uplift_percent)) / 100
    from apps.ledgeraccounts.models import LedgerAccount

    accounts = LedgerAccount.objects.in_bulk({a for a, _ in actual})
    lines = []
    for account in sorted(accounts.values(), key=lambda a: a.code):
        amounts = []
        for m in months:
            last = date(m.year - 1, m.month, 1)
            amounts.append(max(q2(actual.get((account.pk, last), ZERO) * factor), ZERO))
        if any(amounts):
            lines.append({"account": account, "amounts": amounts})
    write_lines(budget, lines)
    return budget


def versus_actual(budget: Budget, through: date | None = None) -> dict:
    months = month_starts(budget.fiscal_year)
    today = timezone.localdate()
    through = through or today
    ytd_months = sum(1 for m in months if m <= through.replace(day=1)) or 0
    lines = list(budget.lines.select_related("account"))
    actual = _ledger(budget.workspace, start=budget.fiscal_year.start_date, end=budget.fiscal_year.end_date, cost_center=budget.cost_center,
                     project=budget.project, accounts=[line.account_id for line in lines])
    rows, totals = [], {"income": [ZERO] * 4, "expense": [ZERO] * 4}
    for line in lines:
        planned = [Decimal(a) for a in line.amounts]
        real = [actual.get((line.account_id, m), ZERO) for m in months]
        ytd_budget, ytd_actual = sum(planned[:ytd_months], ZERO), sum(real[:ytd_months], ZERO)
        kind = line.account.account_type
        variance = (ytd_actual - ytd_budget) if kind == "income" else (ytd_budget - ytd_actual)
        rows.append({
            "account_id": line.account_id, "code": line.account.code, "name": line.account.name, "kind": kind,
            "budget": planned, "actual": real, "budget_total": line.total, "actual_total": sum(real, ZERO),
            "ytd_budget": ytd_budget, "ytd_actual": ytd_actual, "variance": variance, "favourable": variance >= 0,
            "used_percent": q2(sum(real, ZERO) / line.total * 100) if line.total else None,
        })
        t = totals[kind]
        t[0] += line.total
        t[1] += sum(real, ZERO)
        t[2] += ytd_budget
        t[3] += ytd_actual
    return {
        "months": months, "ytd_months": ytd_months, "rows": rows,
        "income": {"budget": totals["income"][0], "actual": totals["income"][1], "ytd_budget": totals["income"][2], "ytd_actual": totals["income"][3]},
        "expense": {"budget": totals["expense"][0], "actual": totals["expense"][1], "ytd_budget": totals["expense"][2], "ytd_actual": totals["expense"][3]},
    }


def check(workspace, *, account, on: date, amount=ZERO, cost_center=None, project=None) -> dict:
    """How much of the approved budget for an expense account is left, and whether `amount` would go over."""
    budget = (Budget.objects.filter(workspace=workspace, status=S.APPROVED, fiscal_year__start_date__lte=on, fiscal_year__end_date__gte=on,
                                    cost_center=cost_center, project=project).select_related("fiscal_year").first())
    line = budget.lines.filter(account=account).first() if budget else None
    if line is None:
        return {"budgeted": False, "budget_id": None, "budget_name": None, "month_budget": None, "month_actual": None, "year_budget": None,
                "year_actual": None, "remaining": None, "would_exceed": False}
    months = month_starts(budget.fiscal_year)
    index = next((i for i, m in enumerate(months) if m == on.replace(day=1)), 0)
    actual = _ledger(workspace, start=budget.fiscal_year.start_date, end=budget.fiscal_year.end_date, cost_center=cost_center, project=project,
                     accounts=[account.pk])
    year_actual = sum(actual.values(), ZERO)
    remaining = line.total - year_actual
    return {"budgeted": True, "budget_id": budget.pk, "budget_name": budget.name, "month_budget": Decimal(line.amounts[index]),
            "month_actual": actual.get((account.pk, months[index]), ZERO), "year_budget": line.total, "year_actual": year_actual,
            "remaining": remaining, "would_exceed": Decimal(str(amount)) > remaining}
