"""Employee records for team members: a member picked as a head or supervisor gets a staff record if they lack one."""
from django.db import transaction

from apps.sequences.services import next_value

from .models import Employee


@transaction.atomic
def employee_for_membership(membership) -> Employee:
    existing = Employee.objects.filter(membership=membership).first()
    if existing is not None:
        return existing
    first, _, last = (membership.user.full_name or membership.user.email.split("@")[0]).strip().partition(" ")
    return Employee.objects.create(workspace=membership.workspace, created_by=membership.user, membership=membership,
                                   staff_number=next_value(membership.workspace, "employee"), first_name=first[:80] or "Member",
                                   last_name=(last or "-")[:80], email=membership.user.email)
