"""
Emails to a business's Owners and Admins about its subscription: the trial ending, payment coming due, a missed
payment, and the business going read-only. Each is sent once (recorded in `reminders_sent`). Sent by the daily pass;
MannaBooks staff can also send the current one from the admin.
"""
from datetime import date, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import Subscription

S = Subscription.Status


def _fmt(d: date) -> str:
    return f"{d:%d %b %Y}"


def due(sub: Subscription, today: date) -> tuple[str, str, str] | None:
    """(key, subject, message) of the reminder this subscription needs today, or None."""
    if sub.complimentary or sub.workspace.blocked_at:
        return None
    name, plan = sub.workspace.name, sub.plan.name
    how = (f"Pay in MannaBooks (Organisation > Plan and billing), or by M-Pesa Paybill with account number {sub.account_number}.")
    if sub.status == S.TRIALING and sub.trial_ends_on:
        days = (sub.trial_ends_on - today).days
        if days in (7, 1):
            return (f"trial-{days}:{sub.trial_ends_on}", f"{name}: your MannaBooks trial ends {'tomorrow' if days == 1 else 'in 7 days'}",
                    f"The free trial of every MannaBooks feature for {name} ends on {_fmt(sub.trial_ends_on)}. Then it moves to the Free plan "
                    f"unless you choose a paid plan. {how}")
        return None
    if sub.plan.is_free or not sub.paid_until:
        return None
    days = (sub.paid_until - today).days
    if sub.status == S.ACTIVE and days in (7, 1):
        return (f"due-{days}:{sub.paid_until}", f"{name}: your {plan} plan renews {'tomorrow' if days == 1 else 'in 7 days'}",
                f"The {plan} plan for {name} is paid up to {_fmt(sub.paid_until)}. To keep using it without interruption, pay before then. {how}")
    if sub.status == S.PAST_DUE:
        grace_end = sub.paid_until + timedelta(days=settings.GRACE_DAYS)
        return (f"overdue:{sub.paid_until}", f"{name}: your MannaBooks payment is due",
                f"The {plan} plan for {name} was paid up to {_fmt(sub.paid_until)}. Please pay by {_fmt(grace_end)}; after that the business "
                f"becomes read-only (you can still see and export everything). {how}")
    if sub.status == S.READ_ONLY:
        return (f"readonly:{sub.paid_until}", f"{name} is read-only until paid",
                f"{name} is now read-only because the {plan} plan hasn't been paid since {_fmt(sub.paid_until)}. Nothing is lost: pay and "
                f"everything works again at once, or move to the Free plan. {how}")
    return None


def recipients(sub: Subscription) -> list[str]:
    from apps.memberships.models import Membership

    people = Membership.objects.filter(workspace=sub.workspace, status="active").select_related("user", "role")
    emails = {m.user.email for m in people if m.has_perm("workspace.manage")}
    emails.add(sub.workspace.owner.email)
    return sorted(e for e in emails if e)


def _send(sub: Subscription, key: str, subject: str, message: str) -> None:
    to = recipients(sub)
    body = f"{message}\n\nMannaBooks\n{settings.FRONTEND_URL}/w/{sub.workspace.slug}/billing"
    transaction.on_commit(lambda: send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, to, fail_silently=True))
    sub.reminders_sent = [*sub.reminders_sent[-20:], key]
    sub.save(update_fields=["reminders_sent", "updated_at"])


def send_due(today: date | None = None) -> int:
    today = today or timezone.localdate()
    sent = 0
    for sub in Subscription.objects.select_related("plan", "workspace__owner").filter(complimentary=False).exclude(status=S.CANCELLED):
        found = due(sub, today)
        if found and found[0] not in sub.reminders_sent:
            _send(sub, *found)
            sent += 1
    return sent


def send_now(sub: Subscription) -> bool:
    """Staff asked for it: send what applies today (again if already sent); for an active plan, a renewal notice."""
    today = timezone.localdate()
    found = due(sub, today)
    if found is None and sub.status == S.ACTIVE and sub.paid_until and not sub.complimentary and not sub.plan.is_free:
        found = (f"manual:{today}", f"{sub.workspace.name}: your {sub.plan.name} plan renews on {_fmt(sub.paid_until + timedelta(days=1))}",
                 f"The {sub.plan.name} plan for {sub.workspace.name} is paid up to {_fmt(sub.paid_until)}. Pay in MannaBooks (Organisation > Plan "
                 f"and billing), or by M-Pesa Paybill with account number {sub.account_number}.")
    if found is None and sub.status == S.TRIALING and sub.trial_ends_on:
        found = (f"manual:{today}", f"{sub.workspace.name}: your MannaBooks trial ends {_fmt(sub.trial_ends_on)}",
                 f"The free trial for {sub.workspace.name} ends on {_fmt(sub.trial_ends_on)}. Choose a plan in Organisation > Plan and billing.")
    if found is None:
        return False
    _send(sub, *found)
    return True


def upcoming(days: int = 14) -> list[Subscription]:
    """Trials ending and paid plans renewing within `days`, plus everything already behind."""
    today = timezone.localdate()
    end = today + timedelta(days=days)
    qs = Subscription.objects.select_related("plan", "workspace__owner").filter(complimentary=False).exclude(status=S.CANCELLED)
    soon = [s for s in qs if (s.status == S.TRIALING and s.trial_ends_on and s.trial_ends_on <= end)
            or (s.status == S.ACTIVE and not s.plan.is_free and s.paid_until and s.paid_until <= end)
            or s.status in (S.PAST_DUE, S.READ_ONLY)]
    return sorted(soon, key=lambda s: (s.trial_ends_on if s.status == S.TRIALING else s.paid_until) or today)
