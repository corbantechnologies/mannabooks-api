"""Platform admin: what MannaBooks staff can do to businesses, users and subscriptions, each recorded in PlatformAction."""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO

from .models import PlatformAction


def record(actor, action: str, target, details: dict | None = None) -> PlatformAction:
    return PlatformAction.objects.create(actor=actor, action=action, target_type=target.__class__.__name__.lower(), target_id=str(target.pk),
                                         target_label=str(target)[:200], details=details or {})


def businesses(search: str = "", status: str = "", plan: str = ""):
    from apps.workspaces.models import Workspace

    qs = (Workspace.objects.select_related("owner", "subscription__plan")
          .annotate(members=Count("memberships", filter=Q(memberships__status="active"), distinct=True))
          .order_by("-created_at"))
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(slug__icontains=search) | Q(owner__email__icontains=search) | Q(kra_pin__icontains=search)
                       | Q(subscription__account_number__iexact=search))
    if status == "blocked":
        qs = qs.filter(blocked_at__isnull=False)
    elif status:
        qs = qs.filter(subscription__status=status)
    if plan:
        qs = qs.filter(subscription__plan__key=plan)
    return qs


def last_active(workspace):
    from apps.auditlogs.models import AuditLog

    return AuditLog.objects.filter(workspace=workspace).aggregate(m=Max("created_at"))["m"]


def stats() -> dict:
    from apps.subscriptionpayments.models import SubscriptionPayment
    from apps.subscriptions.models import Subscription
    from apps.supporttickets.models import SupportTicket
    from apps.workspaces.models import Workspace

    subs = Subscription.objects.select_related("plan")
    paying = subs.filter(status="active", complimentary=False, plan__is_free=False)
    mrr = sum(((s.plan.price_yearly / 12) if s.cycle == "yearly" else s.plan.price_monthly) * (1 - s.discount_percent / 100) for s in paying)
    month_start = timezone.localdate().replace(day=1)
    return {
        "businesses": Workspace.objects.filter(is_active=True).count(),
        "new_this_month": Workspace.objects.filter(created_at__date__gte=month_start).count(),
        "trialing": subs.filter(status="trialing").count(),
        "paying": paying.count(),
        "free": subs.filter(plan__is_free=True).count(),
        "complimentary": subs.filter(complimentary=True).count(),
        "past_due": subs.filter(status__in=["past_due", "read_only"]).count(),
        "blocked": Workspace.objects.filter(blocked_at__isnull=False).count(),
        "mrr": Decimal(mrr).quantize(Decimal("0.01")) if mrr else ZERO,
        "collected_this_month": SubscriptionPayment.objects.filter(status="completed", paid_at__date__gte=month_start).aggregate(s=Sum("amount"))["s"] or ZERO,
        "payments_to_reconcile": SubscriptionPayment.objects.filter(status="pending").exclude(note="").count(),
        "open_tickets": SupportTicket.objects.filter(status__in=["open", "waiting"]).count(),
        "urgent_tickets": SupportTicket.objects.filter(status="open", priority__in=["high", "urgent"]).count(),
    }


@transaction.atomic
def business_action(workspace, action: str, data: dict, staff) -> None:
    from apps.plans.models import Plan
    from apps.subscriptions import services as subs

    sub = subs.of(workspace)
    if action == "block":
        reason = (data.get("reason") or "").strip()
        if not reason:
            raise BusinessRuleError("Say why the business is blocked; its users see the reason.")
        workspace.blocked_at, workspace.blocked_reason = timezone.now(), reason[:255]
        workspace.save(update_fields=["blocked_at", "blocked_reason", "updated_at"])
    elif action == "unblock":
        workspace.blocked_at, workspace.blocked_reason = None, ""
        workspace.save(update_fields=["blocked_at", "blocked_reason", "updated_at"])
    elif action == "change_plan":
        plan = Plan.objects.filter(key=data.get("plan")).first()
        if plan is None:
            raise BusinessRuleError("Choose a plan.")
        sub.plan = plan
        if sub.status in ("past_due", "read_only") and (plan.is_free or sub.complimentary):
            sub.status = "active"
        sub.save(update_fields=["plan", "status", "updated_at"])
    elif action == "extend_trial":
        days = int(data.get("days") or 0)
        if not 1 <= days <= 90:
            raise BusinessRuleError("Extend by 1 to 90 days.")
        base = max(sub.trial_ends_on or timezone.localdate(), timezone.localdate())
        sub.trial_ends_on, sub.status = base + timedelta(days=days), "trialing"
        sub.save(update_fields=["trial_ends_on", "status", "updated_at"])
    elif action == "set_discount":
        percent = Decimal(str(data.get("discount_percent") or 0))
        if not 0 <= percent <= 100:
            raise BusinessRuleError("Use a discount from 0 to 100%.")
        sub.discount_percent = percent
        sub.save(update_fields=["discount_percent", "updated_at"])
    elif action == "set_complimentary":
        sub.complimentary = bool(data.get("complimentary"))
        sub.complimentary_until = data.get("until") if sub.complimentary else None
        if sub.complimentary:
            if data.get("plan"):  # full access for this business: usually the top plan
                found = Plan.objects.filter(key=data["plan"]).first()
                sub.plan = found or sub.plan
            sub.status = "active"
            if data.get("note"):
                sub.notes = "\n".join(x for x in [sub.notes, f"Complimentary: {data['note']}"] if x)
        else:
            subs.end_complimentary(sub)
        sub.save(update_fields=["complimentary", "complimentary_until", "plan", "status", "notes", "updated_at"])
    elif action == "send_reminder":
        from apps.subscriptions.reminders import send_now

        if not send_now(sub):
            raise BusinessRuleError("Nothing to remind about: the business is on a trial far from its end, free, complimentary, or paid well ahead.")
    elif action == "record_payment":
        plan = Plan.objects.filter(key=data.get("plan") or sub.plan.key).first()
        subs.record_manual(sub, plan, cycle=data.get("cycle") or "monthly", periods=int(data.get("periods") or 1),
                           amount=Decimal(str(data.get("amount") or 0)), method=data.get("method") or "bank", reference=data.get("reference", ""),
                           note=data.get("note", ""), staff=staff)
    elif action == "move_to_free":
        subs.move_to_free(sub)
    elif action == "note":
        sub.notes = (data.get("notes") or "").strip()
        sub.save(update_fields=["notes", "updated_at"])
    else:
        raise BusinessRuleError("Unknown action.")
    record(staff, action, workspace, {k: str(v) for k, v in data.items()})


@transaction.atomic
def payment_action(payment, action: str, data: dict, staff) -> None:
    from apps.subscriptions import services as subs

    if action == "complete":
        if payment.status != "pending":
            raise BusinessRuleError("Only a pending payment can be completed.")
        if data.get("periods"):
            payment.periods = int(data["periods"])
        payment.note = (data.get("note") or payment.note)[:255]
        payment.recorded_by = staff
        payment.save(update_fields=["periods", "note", "recorded_by", "updated_at"])
        subs.complete(payment, reference=data.get("reference", ""))
    elif action == "fail":
        if payment.status != "pending":
            raise BusinessRuleError("Only a pending payment can be marked failed.")
        payment.status, payment.note = "failed", (data.get("note") or "Marked failed by staff")[:255]
        payment.save(update_fields=["status", "note", "updated_at"])
    elif action == "refund":
        if payment.status != "completed":
            raise BusinessRuleError("Only a completed payment can be refunded.")
        payment.status, payment.note = "refunded", (data.get("note") or "Refunded")[:255]
        payment.save(update_fields=["status", "note", "updated_at"])
        sub = payment.subscription
        if payment.covers_from and sub.paid_until and sub.paid_until == payment.covers_to:  # take back the time it paid for
            sub.paid_until = payment.covers_from - timedelta(days=1)
            sub.save(update_fields=["paid_until", "updated_at"])
    else:
        raise BusinessRuleError("Unknown action.")
    record(staff, f"payment_{action}", payment, {k: str(v) for k, v in data.items()})


def users(search: str = "", show: str = ""):
    from apps.accounts.models import User

    qs = User.objects.annotate(businesses=Count("owned_workspaces", filter=Q(owned_workspaces__is_active=True), distinct=True),
                               memberships_count=Count("memberships", filter=Q(memberships__status="active"), distinct=True)).order_by("-date_joined")
    if search:
        qs = qs.filter(Q(email__icontains=search) | Q(full_name__icontains=search) | Q(phone__icontains=search))
    if show == "full_access":
        qs = qs.filter(full_access=True)
    elif show == "staff":
        qs = qs.filter(is_staff=True)
    elif show == "blocked":
        qs = qs.filter(is_active=False)
    return qs


def user_action(user, action: str, staff, note: str = "") -> None:
    from apps.subscriptions.services import set_full_access

    if action in ("block", "unblock"):
        if user.is_staff and action == "block":
            raise BusinessRuleError("MannaBooks staff can't be blocked here. Remove their staff access first.")
        user.is_active = action == "unblock"
        user.save(update_fields=["is_active"])
        details = {}
    elif action in ("grant_full_access", "revoke_full_access"):
        if action == "grant_full_access" and not note.strip():
            raise BusinessRuleError("Say why (partner, accountant, MannaBooks team...). It is kept with the account.")
        details = {"businesses": set_full_access(user, action == "grant_full_access", note), "note": note}
    elif action in ("make_staff", "remove_staff"):
        if not staff.is_superuser:
            raise BusinessRuleError("Only a MannaBooks superuser can give or remove staff access.")
        if user.pk == staff.pk:
            raise BusinessRuleError("You can't change your own staff access.")
        user.is_staff = action == "make_staff"
        user.save(update_fields=["is_staff"])
        details = {}
    else:
        raise BusinessRuleError("Unknown action.")
    record(staff, f"user_{action}", user, details)
