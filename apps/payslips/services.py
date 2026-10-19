import calendar
from datetime import date
from decimal import Decimal

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.statutoryrates.services import compute, rates_on

from .models import Payslip


def _unpaid_days(employee, year, month) -> Decimal:
    from apps.leaverequests.models import LeaveRequest
    from apps.leaverequests.services import working_days

    start, end = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    days = Decimal(0)
    for req in LeaveRequest.objects.filter(employee=employee, leave_type="unpaid", status="approved", start_date__lte=end, end_date__gte=start):
        days += working_days(max(req.start_date, start), min(req.end_date, end))
    return days


def recalculate(slip: Payslip) -> Payslip:
    run = slip.pay_run
    rate = rates_on(slip.workspace, run.pay_date)
    working = sum(1 for d in range(1, calendar.monthrange(run.year, run.month)[1] + 1) if date(run.year, run.month, d).weekday() < 5)
    slip.unpaid_leave_deduction = q2(slip.basic_salary / working * slip.unpaid_leave_days) if working and slip.unpaid_leave_days else ZERO
    earnings = [i for i in slip.items if i["kind"] == "earning"]
    deductions = [i for i in slip.items if i["kind"] == "deduction"]
    basic = slip.basic_salary - slip.unpaid_leave_deduction
    gross = q2(basic + sum(Decimal(str(i["amount"])) for i in earnings))
    taxable = q2(basic + sum(Decimal(str(i["amount"])) for i in earnings if i.get("taxable", True)))
    stat = compute(rate, gross=gross, taxable_earnings=taxable)
    for key, value in stat.items():
        setattr(slip, key, value)
    slip.gross_pay = gross
    slip.other_deductions = q2(sum(Decimal(str(i["amount"])) for i in deductions))
    slip.net_pay = gross - stat["nssf_employee"] - stat["shif"] - stat["housing_levy_employee"] - stat["paye"] - slip.other_deductions
    if slip.net_pay < 0:
        raise BusinessRuleError(f"{slip.employee_name}'s deductions are more than their pay.")
    slip.save()
    return slip


def build(run, employee) -> Payslip:
    pay_to = (f"{employee.bank_name} {employee.bank_account_number}".strip() if employee.pay_method == "bank"
              else employee.mpesa_phone if employee.pay_method == "mpesa" else "Cash")
    slip = Payslip.objects.create(
        workspace=run.workspace, pay_run=run, employee=employee, basic_salary=employee.basic_salary, items=list(employee.recurring_items or []),
        unpaid_leave_days=_unpaid_days(employee, run.year, run.month), employee_name=employee.full_name, staff_number=employee.staff_number,
        kra_pin=employee.kra_pin, pay_method=employee.pay_method, pay_to=pay_to,
    )
    return recalculate(slip)
