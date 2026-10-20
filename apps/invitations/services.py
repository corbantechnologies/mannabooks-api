from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.auditlogs import services as audit
from apps.core.exceptions import BusinessRuleError
from apps.memberships.models import Membership

from .models import Invitation, default_expiry
from .tasks import send_invitation_email


def invite(request, email: str, role, employee=None) -> Invitation:
    workspace = request.workspace
    email = email.strip().lower()
    if role.slug == "owner" and not request.membership.is_owner:
        raise BusinessRuleError("Only an Owner can invite another Owner.")
    if Membership.objects.filter(workspace=workspace, user__email=email).exists():
        raise BusinessRuleError("This person is already a member of the workspace.")
    pending = Invitation.objects.filter(workspace=workspace, email=email, status=Invitation.Status.PENDING).first()
    if pending:
        # Re-inviting refreshes the pending invitation instead of creating a second one.
        pending.role, pending.employee, pending.expires_at = role, employee or pending.employee, default_expiry()
        pending.save(update_fields=["role", "employee", "expires_at", "updated_at"])
        invitation = pending
    else:
        from apps.subscriptions.services import check_seat

        check_seat(workspace, role.slug)
        invitation = Invitation.objects.create(
            workspace=workspace, email=email, role=role, employee=employee, created_by=request.user
        )
    audit.record(request, "create", invitation)
    transaction.on_commit(lambda: send_invitation_email.delay(str(invitation.id)))
    return invitation


def by_token(token: str) -> Invitation:
    invitation = Invitation.objects.select_related("workspace", "role").filter(token=token).first()
    if invitation is None or not invitation.workspace.is_active:
        raise NotFound("This invitation does not exist.")
    return invitation


@transaction.atomic
def accept(request, token: str) -> Membership:
    invitation = by_token(token)
    if invitation.status != Invitation.Status.PENDING:
        raise BusinessRuleError(f"This invitation was already {invitation.get_status_display().lower()}.")
    if invitation.is_expired:
        raise BusinessRuleError("This invitation has expired. Ask for a new one.")
    user = request.user
    if user.email != invitation.email:
        raise PermissionDenied(f"This invitation is for {invitation.email}. Sign in with that email to accept it.")
    membership, _ = Membership.objects.get_or_create(
        workspace=invitation.workspace,
        user=user,
        defaults={"role": invitation.role, "created_by": invitation.created_by},
    )
    if invitation.employee and invitation.employee.membership_id is None:
        invitation.employee.membership = membership
        invitation.employee.save(update_fields=["membership", "updated_at"])
    invitation.status = Invitation.Status.ACCEPTED
    invitation.accepted_by = user
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["status", "accepted_by", "accepted_at", "updated_at"])
    request.workspace = invitation.workspace
    audit.record(request, "create", membership)
    return membership
