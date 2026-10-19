"""
Approval chains. A document's approve service calls `gate`: with no matching rule the document is
approved at once; otherwise a request is opened and each level's approvers decide in turn. When the
last level approves, the document's own approve service runs and `gate` lets it through.
"""
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.approvalrules.models import ApprovalRule
from apps.core.exceptions import BusinessRuleError
from apps.memberships.models import Membership

from .models import ApprovalRequest, ApprovalStep
from .registry import DOCS

R = ApprovalRequest.Status


def _member(workspace, user):
    if user is None:
        return None
    return Membership.objects.filter(workspace=workspace, user=user, status="active").select_related("role").first()


def plan(workspace, doc_type: str, amount, user) -> tuple:
    """(rule, levels) for a document of this amount, or (None, None) when it can be approved directly."""
    rule = (ApprovalRule.objects.filter(workspace=workspace, document_type=doc_type, is_active=True, min_amount__lte=amount)
            .filter(Q(max_amount__isnull=True) | Q(max_amount__gte=amount)).order_by("-min_amount").first())
    if rule is not None:
        return rule, list(rule.levels)
    member = _member(workspace, user)
    if member is not None and not member.is_owner and member.approval_limit > 0 and amount > member.approval_limit:
        return None, [{"kind": "module_in_charge"}]  # above their limit: the module in-charge decides
    return None, None


def _owners(workspace):
    return list(Membership.objects.filter(workspace=workspace, status="active", role__slug="owner").select_related("user"))


def approvers(req: ApprovalRequest, index: int | None = None) -> list[Membership]:
    """The members who may decide at a level. Nobody approves their own request unless they are the only owner."""
    index = req.current_level if index is None else index
    if index >= len(req.levels):
        return []
    cache = req.__dict__.setdefault("_approvers", {})
    if index not in cache:
        cache[index] = _resolve(req, index)
    return cache[index]


def _resolve(req: ApprovalRequest, index: int) -> list[Membership]:
    level, workspace = req.levels[index], req.workspace
    requester = _member(workspace, req.created_by)
    employee = getattr(requester, "employee", None) if requester else None
    found: list[Membership] = []
    kind = level.get("kind")
    active = Membership.objects.filter(workspace=workspace, status="active").select_related("user", "role")
    if kind == "supervisor":
        boss = getattr(employee, "reports_to", None)
        found = [boss.membership] if boss and boss.membership_id else []
    elif kind == "department_head":
        dept = getattr(employee, "department", None)
        head = dept.head if dept else None
        found = [head.membership] if head and head.membership_id else []
    elif kind == "module_in_charge":
        from apps.departments.models import Department

        dept = Department.objects.filter(workspace=workspace, is_active=True, modules__contains=[DOCS[req.document_type].module],
                                         head__membership__isnull=False).select_related("head__membership").first()
        found = [dept.head.membership] if dept else []
    elif kind == "role":
        found = list(active.filter(role_id=level.get("role_id")))
    elif kind == "member":
        found = list(active.filter(pk=level.get("membership_id")))
    elif kind == "owner":
        found = _owners(workspace)
    found = [m for m in found if m.status == "active" and (requester is None or m.pk != requester.pk)]
    return found or [m for m in _owners(workspace) if requester is None or m.pk != requester.pk] or _owners(workspace)


def can_decide(req: ApprovalRequest, user) -> bool:
    return req.status == R.PENDING and any(m.user_id == user.id for m in approvers(req))


def _notify(req: ApprovalRequest, members, subject: str, body: str) -> None:
    emails = [m.user.email for m in members if m.user.email]
    if not emails:
        return
    link = f"{settings.FRONTEND_URL}/w/{req.workspace.slug}/approvals"
    from .tasks import send_approval_email

    text = f"{body}\n\nOpen it: {link}"
    transaction.on_commit(lambda: send_approval_email.delay(subject, text, emails))


def _pending(workspace, doc_type, obj):
    return ApprovalRequest.objects.select_for_update().filter(workspace=workspace, document_type=doc_type, object_id=obj.pk, status=R.PENDING).first()


@transaction.atomic
def submit(workspace, doc_type: str, obj, user) -> ApprovalRequest | None:
    """Open a request for a document. None when no rule applies (it can be approved directly)."""
    spec = DOCS[doc_type]
    if not spec.waiting(obj):
        raise BusinessRuleError(f"This {spec.label.lower()} isn't waiting for approval.")
    existing = _pending(workspace, doc_type, obj)
    if existing is not None:
        return existing
    requester = getattr(obj, "created_by", None) or user
    amount = spec.amount(obj)
    rule, levels = plan(workspace, doc_type, amount, user)  # an approval limit is the limit of whoever is approving
    if levels is None:
        return None
    for level in levels:
        if level.get("kind") == "module_in_charge":
            level["module"] = spec.module
    req = ApprovalRequest.objects.create(workspace=workspace, created_by=requester, document_type=doc_type, object_id=obj.pk,
                                         document_number=str(spec.number(obj))[:80], summary=str(spec.summary(obj))[:255], amount=amount,
                                         rule=rule, levels=levels)
    req.just_created = True
    _notify(req, approvers(req), f"Approval needed: {req.document_number}",
            f"{spec.label} {req.document_number} ({req.summary}, {amount:,.2f}) is waiting for your approval.")
    return req


@transaction.atomic
def gate(doc_type: str, obj, user) -> bool:
    """
    Called by a document's approve service. True: approve it now. False: it has gone into (or moved along)
    the approval chain and stays unapproved for now.
    """
    workspace, spec = obj.workspace, DOCS[doc_type]
    ready = ApprovalRequest.objects.select_for_update().filter(workspace=workspace, document_type=doc_type, object_id=obj.pk,
                                                              status=R.APPROVED, used=False).first()
    if ready is not None:
        ready.used = True
        ready.save(update_fields=["used", "updated_at"])
        if spec.amount(obj) <= ready.amount:
            return True
        # the document grew after it was approved: it goes round again
    req = _pending(workspace, doc_type, obj) or submit(workspace, doc_type, obj, user)
    if req is None:
        return True
    if can_decide(req, user):
        _record(req, user, "approved", "")
        if req.status == R.APPROVED:
            req.used = True
            req.save(update_fields=["used", "updated_at"])
            return True
        return False
    if getattr(req, "just_created", False):
        return False
    names = ", ".join(m.user.full_name for m in approvers(req)) or "the owner"
    raise BusinessRuleError(f"This is waiting for approval from {names}.")


def _record(req: ApprovalRequest, user, decision: str, comment: str) -> None:
    ApprovalStep.objects.create(request=req, level=req.current_level, decision=decision, decided_by=user, comment=comment[:255])
    spec = DOCS[req.document_type]
    if decision == "rejected":
        req.status, req.decided_at = R.REJECTED, timezone.now()
        req.save(update_fields=["status", "decided_at", "updated_at"])
        requester = _member(req.workspace, req.created_by)
        if requester:
            _notify(req, [requester], f"Not approved: {req.document_number}",
                    f"{user.full_name} did not approve {spec.label.lower()} {req.document_number}." + (f" Their note: {comment}" if comment else ""))
        return
    req.current_level += 1
    req.__dict__.pop("_approvers", None)
    if req.current_level >= len(req.levels):
        req.status, req.decided_at = R.APPROVED, timezone.now()
        req.save(update_fields=["current_level", "status", "decided_at", "updated_at"])
        return
    req.save(update_fields=["current_level", "updated_at"])
    _notify(req, approvers(req), f"Approval needed: {req.document_number}",
            f"{spec.label} {req.document_number} ({req.summary}, {req.amount:,.2f}) has been approved by {user.full_name} and now needs yours.")


@transaction.atomic
def decide(req: ApprovalRequest, user, decision: str, comment: str = "") -> ApprovalRequest:
    req = ApprovalRequest.objects.select_for_update().get(pk=req.pk)
    if req.status != R.PENDING:
        raise BusinessRuleError(f"This request is already {req.get_status_display().lower()}.")
    if not can_decide(req, user):
        names = ", ".join(m.user.full_name for m in approvers(req)) or "the owner"
        raise BusinessRuleError(f"This isn't waiting for you. It's waiting for {names}.")
    if decision == "rejected" and not comment.strip():
        raise BusinessRuleError("Say why you're not approving it, so they can fix it.")
    spec = DOCS[req.document_type]
    obj = spec.get(req.workspace, req.object_id)
    if obj is None or not spec.waiting(obj):
        req.status, req.decided_at = R.CANCELLED, timezone.now()
        req.save(update_fields=["status", "decided_at", "updated_at"])
        raise BusinessRuleError(f"This {spec.label.lower()} is no longer waiting for approval, so the request was withdrawn.")
    _record(req, user, decision, comment)
    if req.status == R.APPROVED:
        spec.approve(obj, user)  # its gate finds this approved request and lets it through
    return req


@transaction.atomic
def cancel(req: ApprovalRequest, user, can_manage: bool) -> ApprovalRequest:
    req = ApprovalRequest.objects.select_for_update().get(pk=req.pk)
    if req.status != R.PENDING:
        raise BusinessRuleError("Only a waiting request can be withdrawn.")
    if req.created_by_id != user.id and not can_manage:
        raise BusinessRuleError("Only the person who asked can withdraw it.")
    req.status, req.decided_at = R.CANCELLED, timezone.now()
    req.save(update_fields=["status", "decided_at", "updated_at"])
    return req


def status_for(workspace, doc_type: str, obj, user, membership) -> dict:
    """What a document page shows: whether a chain applies, the latest request, and what this user can do."""
    spec = DOCS[doc_type]
    latest = ApprovalRequest.objects.filter(workspace=workspace, document_type=doc_type, object_id=obj.pk).order_by("-created_at").first()
    waiting = spec.waiting(obj)
    pending = latest if latest is not None and latest.status == R.PENDING else None
    rule, levels = (None, None)
    if waiting and pending is None:
        rule, levels = plan(workspace, doc_type, spec.amount(obj), user)
    from apps.approvalrules.serializers import level_label

    if levels:
        for level in levels:
            if level.get("kind") == "module_in_charge":
                level["module"] = spec.module
    return {
        "required": bool(pending) or bool(levels),
        "rule_name": rule.name if rule else ("Above the approval limit" if levels else None),
        "levels": [level_label(workspace, lvl) for lvl in (levels or [])],
        "request": latest,
        "can_submit": bool(waiting and pending is None and levels and membership.has_perm(spec.submit_perm)),
    }
