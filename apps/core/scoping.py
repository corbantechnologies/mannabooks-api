"""
Team members limited to one department (Membership.limited_department) see only that department's records.

A record belongs to a department when it is tagged with it, through its cost centre (a cost centre belongs to a
department), or through its employee. Records the person created stay visible to them, so nothing they enter
disappears. Records with none of these fields (customers, products, bank accounts) are shared by everyone.
Owners always see the whole business.
"""
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

# Lists that a department limit must not hide (they aren't a department's records).
NOT_SCOPED = {"invitations.Invitation", "memberships.Membership", "budgets.Budget"}


def limited_department(request):
    membership = getattr(request, "membership", None)
    if membership is None or membership.limited_department_id is None or membership.is_owner:
        return None
    return membership.limited_department


def department_filter(model, department, user=None) -> Q | None:
    """The filter that keeps a model's rows belonging to `department`, or None when the model isn't split by department."""
    label = model._meta.label
    if label in NOT_SCOPED:
        return None
    if label == "departments.Department":
        return Q(pk=department.pk)
    fields = {f.name for f in model._meta.get_fields()}
    if label == "journals.JournalLine":
        q = Q(department=department) | Q(department__isnull=True, cost_center__department=department)
    elif "department" in fields:
        q = Q(department=department)
    elif "cost_center" in fields:
        q = Q(cost_center__department=department)
    elif "employee" in fields:
        q = Q(employee__department=department)
    else:
        return None
    if user is not None and "created_by" in fields:
        q |= Q(created_by=user)
    return q


def scope_queryset(qs, request):
    department = limited_department(request)
    if department is None:
        return qs
    q = department_filter(qs.model, department, getattr(request, "user", None))
    return qs.filter(q) if q is not None else qs


def deny_if_limited(request, what: str = "This report") -> None:
    """Company-wide reports (balance sheet, trial balance, ledger, VAT) are closed to someone limited to a department."""
    department = limited_department(request)
    if department is not None:
        raise PermissionDenied(f"{what} covers the whole business; your access is limited to {department.name}.")
