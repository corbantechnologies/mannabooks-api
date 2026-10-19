from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError

from .models import LeaveRequest

S = LeaveRequest.Status


def working_days(start: date, end: date) -> Decimal:
    """Monday to Friday between the dates, inclusive. (Public holidays are not taken off yet.)"""
    days, d = 0, start
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return Decimal(days)


def balance(employee, year: int) -> dict:
    taken = LeaveRequest.objects.filter(employee=employee, leave_type="annual", status=S.APPROVED, start_date__year=year).aggregate(s=Sum("days"))["s"] or 0
    pending = LeaveRequest.objects.filter(employee=employee, leave_type="annual", status=S.PENDING, start_date__year=year).aggregate(s=Sum("days"))["s"] or 0
    return {"year": year, "entitlement": employee.annual_leave_days, "taken": taken, "pending": pending,
            "remaining": employee.annual_leave_days - taken - pending}


def can_decide(membership, request: LeaveRequest) -> bool:
    """Their supervisor, the head of their department, or anyone allowed to approve all leave. Never for their own."""
    employee = request.employee
    if employee.membership_id == membership.id:
        return False
    if membership.has_perm("leave.approve"):
        return True
    me = getattr(membership, "employee", None)
    if me is None:
        return False
    if employee.reports_to_id == me.id:
        return True
    return bool(employee.department_id and employee.department.head_id == me.id)


@transaction.atomic
def request_leave(employee, *, leave_type, start_date, end_date, reason="", user=None) -> LeaveRequest:
    if end_date < start_date:
        raise BusinessRuleError("The last day can't be before the first.")
    days = working_days(start_date, end_date)
    if days <= 0:
        raise BusinessRuleError("Those dates are a weekend.")
    if LeaveRequest.objects.filter(employee=employee, status__in=[S.PENDING, S.APPROVED], start_date__lte=end_date, end_date__gte=start_date).exists():
        raise BusinessRuleError("This overlaps leave already requested or approved.")
    if leave_type == "annual" and days > balance(employee, start_date.year)["remaining"]:
        raise BusinessRuleError(f"Only {balance(employee, start_date.year)['remaining']} annual leave days are left for {start_date.year}.")
    return LeaveRequest.objects.create(workspace=employee.workspace, created_by=user, employee=employee, leave_type=leave_type,
                                       start_date=start_date, end_date=end_date, days=days, reason=reason)


def decide(req: LeaveRequest, *, approve: bool, membership, note="") -> LeaveRequest:
    if req.status != S.PENDING:
        raise BusinessRuleError("This request is already decided.")
    if not can_decide(membership, req):
        raise BusinessRuleError("Only their supervisor, their department head or HR can decide this.")
    req.status = S.APPROVED if approve else S.REJECTED
    req.decided_by, req.decided_at, req.decision_note = membership.user, timezone.now(), note[:255]
    req.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    return req


def cancel(req: LeaveRequest) -> LeaveRequest:
    if req.status not in (S.PENDING, S.APPROVED):
        raise BusinessRuleError("This request can't be cancelled.")
    if req.status == S.APPROVED and req.start_date <= timezone.localdate():
        raise BusinessRuleError("This leave has started. Ask HR to change it.")
    req.status = S.CANCELLED
    req.save(update_fields=["status", "updated_at"])
    return req
