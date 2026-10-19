"""Pay runs: generate payslips, approve (post), pay net salaries, and record statutory remittances."""
import calendar
from datetime import date

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.journals.services import LineInput, post_lines, replace_for_source
from apps.ledgeraccounts.services import system_account

from .models import PayRun

SOURCE = {"source": "payroll", "source_model": "payruns.PayRun"}
REMIT = {"paye": ("paye", "total_paye", "PAYE (KRA)"), "shif": ("shif", "total_shif", "SHIF"), "nssf": ("nssf", "total_nssf", "NSSF"),
         "housing_levy": ("housing_levy", "total_housing_levy", "Housing Levy (KRA)")}


@transaction.atomic
def create(workspace, *, year, month, pay_date=None, user=None) -> PayRun:
    from apps.employees.models import Employee
    from apps.payslips.services import build

    if not 1 <= month <= 12:
        raise BusinessRuleError("Choose a month.")
    if PayRun.objects.filter(workspace=workspace, year=year, month=month).exists():
        raise BusinessRuleError(f"There is already a payroll for {calendar.month_name[month]} {year}.")
    run = PayRun.objects.create(workspace=workspace, created_by=user, year=year, month=month,
                                pay_date=pay_date or date(year, month, calendar.monthrange(year, month)[1]))
    people = Employee.objects.filter(workspace=workspace, on_payroll=True, basic_salary__gt=0).exclude(status="exited")
    if not people.exists():
        raise BusinessRuleError("No employees are on payroll. On each employee, tick On payroll and enter their basic salary.")
    for employee in people:
        build(run, employee)
    refresh_totals(run)
    return run


def refresh_totals(run: PayRun) -> PayRun:
    t = run.payslips.aggregate(g=Sum("gross_pay"), p=Sum("paye"), s=Sum("shif"), ne=Sum("nssf_employee"), nr=Sum("nssf_employer"),
                               he=Sum("housing_levy_employee"), hr=Sum("housing_levy_employer"), o=Sum("other_deductions"), n=Sum("net_pay"))
    z = {k: (v or ZERO) for k, v in t.items()}
    run.gross_pay, run.total_paye, run.total_shif = z["g"], z["p"], z["s"]
    run.total_nssf, run.total_housing_levy, run.total_other_deductions, run.net_pay = z["ne"] + z["nr"], z["he"] + z["hr"], z["o"], z["n"]
    run.employer_cost = z["g"] + z["nr"] + z["hr"]
    run.save()
    return run


@transaction.atomic
def approve(run: PayRun, user) -> PayRun:
    run = PayRun.objects.select_for_update().get(pk=run.pk)
    if run.status != PayRun.Status.DRAFT:
        raise BusinessRuleError("This payroll is already approved.")
    if not run.payslips.exists():
        raise BusinessRuleError("There are no payslips.")
    from apps.approvalrequests.services import gate

    if not gate("pay_run", run, user):
        return run
    ws, label = run.workspace, f"Payroll {calendar.month_name[run.month]} {run.year}"
    t = run.payslips.aggregate(nr=Sum("nssf_employer"), hr=Sum("housing_levy_employer"))
    employer = (t["nr"] or ZERO) + (t["hr"] or ZERO)
    lines = [LineInput(account=system_account(ws, "salaries"), debit=run.gross_pay, description=f"{label}: gross pay")]
    if employer:
        lines.append(LineInput(account=system_account(ws, "salaries"), debit=employer, description=f"{label}: employer NSSF and Housing Levy"))
    credits = [("paye", run.total_paye, "PAYE"), ("shif", run.total_shif, "SHIF"), ("nssf", run.total_nssf, "NSSF"),
               ("housing_levy", run.total_housing_levy, "Housing Levy"), ("salaries_payable", run.net_pay, "net pay")]
    lines += [LineInput(account=system_account(ws, key), credit=amount, description=f"{label}: {what}") for key, amount, what in credits if amount]
    if run.total_other_deductions:
        lines.append(LineInput(account=system_account(ws, "payroll_deductions"), credit=run.total_other_deductions, description=f"{label}: other deductions"))
    replace_for_source(ws, **SOURCE, source_id=str(run.pk), entry_date=run.pay_date, reference=f"PAY-{run.year}-{run.month:02d}",
                       description=label, lines=lines, user=user)
    run.status, run.approved_by, run.approved_at = PayRun.Status.APPROVED, user, timezone.now()
    run.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return run


@transaction.atomic
def reopen(run: PayRun, user=None) -> PayRun:
    if run.status != PayRun.Status.APPROVED:
        raise BusinessRuleError("Only an approved, unpaid payroll can be reopened.")
    replace_for_source(run.workspace, **SOURCE, source_id=str(run.pk), entry_date=run.pay_date, description="", lines=[], user=user)
    run.status, run.approved_by, run.approved_at = PayRun.Status.DRAFT, None, None
    run.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return run


@transaction.atomic
def pay(run: PayRun, *, bank_account, paid_on, user=None) -> PayRun:
    """Net salaries sent from one account (the bank's bulk payment, or M-Pesa B2C)."""
    if run.status != PayRun.Status.APPROVED:
        raise BusinessRuleError("Approve the payroll before paying it.")
    label = f"Salaries {calendar.month_name[run.month]} {run.year}"
    post_lines(run.workspace, entry_date=paid_on, description=label, source="payroll_payment", source_model="payruns.PayRun.pay",
               source_id=str(run.pk), reference=f"PAY-{run.year}-{run.month:02d}", user=user,
               lines=[LineInput(account=system_account(run.workspace, "salaries_payable"), debit=run.net_pay, description=label),
                      LineInput(account=bank_account.ledger_account, credit=run.net_pay, description=label)])
    run.status, run.paid_from, run.paid_at = PayRun.Status.PAID, bank_account, paid_on
    run.save(update_fields=["status", "paid_from", "paid_at", "updated_at"])
    return run


@transaction.atomic
def remit(run: PayRun, *, kind: str, bank_account, paid_on, reference="", user=None) -> PayRun:
    """Record paying a statutory deduction (PAYE, SHIF, NSSF or Housing Levy) for this payroll."""
    if run.status == PayRun.Status.DRAFT:
        raise BusinessRuleError("Approve the payroll first.")
    if kind not in REMIT:
        raise BusinessRuleError("Choose PAYE, SHIF, NSSF or Housing Levy.")
    if kind in run.remittances:
        raise BusinessRuleError("This is already recorded as paid.")
    key, field, label = REMIT[kind]
    amount = q2(getattr(run, field))
    if amount <= 0:
        raise BusinessRuleError("Nothing to pay.")
    text = f"{label} for {calendar.month_name[run.month]} {run.year}"
    post_lines(run.workspace, entry_date=paid_on, description=text, source="payroll_remittance", source_model=f"payruns.PayRun.{kind}",
               source_id=str(run.pk), reference=reference or text[:60], user=user,
               lines=[LineInput(account=system_account(run.workspace, key), debit=amount, description=text),
                      LineInput(account=bank_account.ledger_account, credit=amount, description=text)])
    run.remittances = {**run.remittances, kind: {"amount": str(amount), "date": paid_on.isoformat(), "reference": reference, "account": bank_account.name}}
    run.save(update_fields=["remittances", "updated_at"])
    return run
