"""
What a business's plan lets it do, what it costs, and how payments move it along.

- Every new business starts a trial of the top plan; when the trial ends it moves to the free plan unless it paid.
- A paid plan runs to `paid_until`. After that it is `past_due`; after the grace days it becomes read-only
  (everything can still be seen and exported, nothing changed) until it pays or moves to the free plan.
- Blocked businesses (by MannaBooks staff) can't be used at all.
"""
import calendar
import random
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2

from .models import Subscription

S = Subscription.Status
TOP_PLAN, FREE_PLAN = "kampuni", "free"
FREE_SEAT_ROLES = ("accountant", "self-service")  # accountants and staff who only see their own pay don't use up seats


def add_months(start: date, months: int) -> date:
    month = start.month - 1 + months
    year, month = start.year + month // 12, month % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _account_number() -> str:
    for _ in range(50):
        number = f"MB{random.randint(100000, 999999)}"
        if not Subscription.objects.filter(account_number=number).exists():
            return number
    raise BusinessRuleError("Couldn't make an account number. Try again.")


def plan(key: str):
    from apps.plans.models import Plan

    found = Plan.objects.filter(key=key).first()
    if found is None:
        raise BusinessRuleError(f"The {key} plan is missing. Add it in the MannaBooks admin.")
    return found


def start(workspace) -> Subscription:
    """A new business: a trial of the top plan (or, if its owner was given full access, the top plan free)."""
    if getattr(workspace.owner, "full_access", False):
        return Subscription.objects.create(workspace=workspace, plan=plan(TOP_PLAN), status=S.ACTIVE, complimentary=True, account_number=_account_number(),
                                           notes=f"Full access given to the owner: {workspace.owner.full_access_note}".strip(": "))
    return Subscription.objects.create(
        workspace=workspace, plan=plan(TOP_PLAN), status=S.TRIALING, account_number=_account_number(),
        trial_ends_on=timezone.localdate() + timedelta(days=settings.TRIAL_DAYS),
    )


def end_complimentary(sub: Subscription, today: date | None = None) -> None:
    """Back to normal billing (not saved here). Without paid time, a short trial gives the business notice before it is due."""
    today = today or timezone.localdate()
    sub.complimentary, sub.complimentary_until = False, None
    if not (sub.paid_until and sub.paid_until >= today) and not sub.plan.is_free:
        sub.status, sub.trial_ends_on = S.TRIALING, today + timedelta(days=settings.GRACE_DAYS)


def set_full_access(user, on: bool, note: str = "") -> int:
    """Give or take back full access: every business the person owns goes on (or comes off) the free top plan. Returns how many."""
    user.full_access, user.full_access_note = on, (note.strip()[:255] if on else "")
    user.save(update_fields=["full_access", "full_access_note"])
    count = 0
    for ws in user.owned_workspaces.filter(is_active=True):
        sub = of(ws)
        if on:
            sub.plan, sub.complimentary, sub.status = plan(TOP_PLAN), True, S.ACTIVE
        else:
            end_complimentary(sub)
        sub.save()
        count += 1
    return count


def of(workspace) -> Subscription:
    sub = Subscription.objects.select_related("plan", "coupon").filter(workspace=workspace).first()
    return sub or start(workspace)


def usage(workspace) -> dict:
    from apps.invoices.models import Invoice
    from apps.memberships.models import Membership
    from apps.quotations.models import Quotation
    from apps.receipts.models import Receipt

    month_start = timezone.localdate().replace(day=1)
    documents = sum(model.objects.filter(workspace=workspace, created_at__date__gte=month_start).count() for model in (Invoice, Receipt, Quotation))
    users = Membership.objects.filter(workspace=workspace, status="active").exclude(role__slug__in=FREE_SEAT_ROLES).count()
    return {"documents_this_month": documents, "users": users}


# ---------------------------------------------------------------- limits
def check_write(workspace, permission: str | None) -> None:
    """Raised before a change: the plan must be paid up and include the module the change belongs to."""
    from apps.core.catalog import PERMISSION_APP_MODULE

    sub = of(workspace)
    if not sub.can_write:
        raise BusinessRuleError("This business is read-only until the subscription is paid. Go to Settings > Plan and billing.",
                                code="subscription_read_only")
    module = PERMISSION_APP_MODULE.get((permission or "").split(".")[0])
    if module and not sub.plan.includes(module):
        raise BusinessRuleError(f"The {sub.plan.name} plan doesn't include this. Upgrade in Settings > Plan and billing.", code="plan_upgrade")


def check_documents(workspace) -> None:
    """Before a new invoice, cash sale or quotation: the plan's monthly document limit."""
    sub = of(workspace)
    limit = sub.plan.max_documents_month
    if limit is not None and usage(workspace)["documents_this_month"] >= limit:
        raise BusinessRuleError(f"The {sub.plan.name} plan includes {limit} invoices, cash sales and quotations a month, and this month's are used. "
                                "Upgrade in Settings > Plan and billing.", code="plan_upgrade")


def check_seat(workspace, role_slug: str) -> None:
    """Before adding or inviting a team member."""
    from apps.invitations.models import Invitation

    if role_slug in FREE_SEAT_ROLES:
        return
    sub = of(workspace)
    limit = sub.plan.max_users
    if limit is None:
        return
    pending = Invitation.objects.filter(workspace=workspace, status="pending").exclude(role__slug__in=FREE_SEAT_ROLES).count()
    if usage(workspace)["users"] + pending >= limit:
        raise BusinessRuleError(f"The {sub.plan.name} plan has {limit} team {'member' if limit == 1 else 'members'}. Accountants and self-service staff "
                                "don't count. Upgrade in Settings > Plan and billing for more.", code="plan_upgrade")


def has_feature(workspace, feature: str) -> bool:
    return feature in (of(workspace).plan.features or [])


# ---------------------------------------------------------------- prices
def payroll_addon(workspace, p) -> Decimal:
    """The payroll add-on for one month: per employee on the payroll, with a minimum, once payroll is in use."""
    from apps.employees.models import Employee

    if not p.payroll_per_employee or not p.includes("people"):
        return ZERO
    staff = Employee.objects.filter(workspace=workspace, status="active", on_payroll=True).count()
    if not staff:
        return ZERO
    return max(q2(p.payroll_per_employee * staff), p.payroll_minimum)


def find_coupon(code: str, p):
    from apps.coupons.models import Coupon

    code = (code or "").strip().upper()
    if not code:
        return None
    c = Coupon.objects.filter(code__iexact=code, is_active=True).prefetch_related("plans").first()
    today = timezone.localdate()
    if c is None or (c.valid_until and c.valid_until < today) or (c.max_redemptions is not None and c.times_redeemed >= c.max_redemptions):
        raise BusinessRuleError("That code isn't valid.")
    if c.plans.exists() and p not in c.plans.all():
        raise BusinessRuleError(f"That code isn't for the {p.name} plan.")
    return c


def quote(sub: Subscription, p, *, cycle: str, periods: int = 1, coupon_code: str = "") -> dict:
    if p.is_free:
        raise BusinessRuleError("The free plan has nothing to pay.")
    if periods < 1 or periods > (24 if cycle == "monthly" else 3):
        raise BusinessRuleError("Pay for 1 to 24 months, or 1 to 3 years.")
    base = p.price_yearly if cycle == "yearly" else p.price_monthly
    months = 12 if cycle == "yearly" else 1
    addon = payroll_addon(sub.workspace, p) * months
    list_price = q2((base + addon) * periods)
    coupon = find_coupon(coupon_code, p) if coupon_code else (sub.coupon if sub.coupon and sub.coupon_payments_left != 0 else None)
    percent = max(sub.discount_percent, coupon.percent_off if coupon else ZERO)
    discount = q2(list_price * percent / 100) + (q2(coupon.amount_off * periods) if coupon else ZERO)
    discount = min(discount, list_price)
    # M-Pesa takes whole shillings: round the amount due down in the customer's favour
    amount = Decimal(int(list_price - discount))
    return {"plan": p, "cycle": cycle, "periods": periods, "base": base, "payroll_addon": addon, "list_price": list_price,
            "discount": list_price - amount, "amount": amount, "coupon": coupon}


# ---------------------------------------------------------------- payments
def platform_workspace():
    from apps.workspaces.models import Workspace

    slug = settings.PLATFORM_WORKSPACE_SLUG
    return Workspace.objects.filter(slug=slug).first() if slug else None


@transaction.atomic
def pay_by_mpesa(sub: Subscription, p, *, cycle: str, periods: int, phone: str, coupon_code: str = "", user=None):
    """An M-Pesa prompt to the payer's phone, for MannaBooks' paybill, with the business's account number."""
    from apps.mpesatransactions.services import request_payment
    from apps.subscriptionpayments.models import SubscriptionPayment

    home = platform_workspace()
    if home is None:
        raise BusinessRuleError(f"Paying in the app isn't available yet. Pay to the MannaBooks paybill with account {sub.account_number}, "
                                "or contact MannaBooks.")
    q = quote(sub, p, cycle=cycle, periods=periods, coupon_code=coupon_code)
    if q["amount"] < 1:
        raise BusinessRuleError("Nothing to pay after the discount. Contact MannaBooks to apply it.")
    tx = request_payment(home, phone=phone, amount=q["amount"], reference=sub.account_number)
    return SubscriptionPayment.objects.create(
        subscription=sub, plan=p, cycle=cycle, periods=periods, list_price=q["list_price"], discount=q["discount"], amount=q["amount"],
        coupon=q["coupon"], method="mpesa", status="pending", mpesa_transaction=tx, paid_by=user,
    )


@transaction.atomic
def complete(payment, *, reference: str = "") -> None:
    """A payment went through: the plan runs on from the end of the paid period (or from today)."""
    from apps.subscriptionpayments.models import SubscriptionPayment

    payment = SubscriptionPayment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == "completed":
        return
    sub = Subscription.objects.select_for_update().get(pk=payment.subscription_id)
    today = timezone.localdate()
    begin = max(today, (sub.paid_until + timedelta(days=1)) if sub.paid_until else today)
    months = payment.periods * (12 if payment.cycle == "yearly" else 1)
    end = add_months(begin, months) - timedelta(days=1)
    payment.status, payment.covers_from, payment.covers_to = "completed", begin, end
    payment.paid_at = payment.paid_at or timezone.now()
    payment.reference = reference or payment.reference
    payment.save()
    sub.plan, sub.cycle, sub.paid_until, sub.status = payment.plan, payment.cycle, end, S.ACTIVE
    if payment.coupon_id:
        coupon = payment.coupon
        if sub.coupon_id != coupon.pk:  # first use of this code by this business
            coupon.times_redeemed += 1
            coupon.save(update_fields=["times_redeemed", "updated_at"])
            sub.coupon, sub.coupon_payments_left = coupon, coupon.payments
        if sub.coupon_payments_left:
            sub.coupon_payments_left -= 1
    sub.save()


def mpesa_settled(tx) -> None:
    """
    Called when an M-Pesa payment reaches MannaBooks' own workspace: a prompt we sent (pending payment), or money
    paid straight to the paybill with a subscription account number. Anything unclear waits for staff to reconcile.
    """
    from apps.subscriptionpayments.models import SubscriptionPayment

    home = platform_workspace()
    if home is None or tx.workspace_id != home.pk or tx.status != "completed":
        return
    pending = SubscriptionPayment.objects.filter(mpesa_transaction=tx, status="pending").first()
    if pending is not None:
        if tx.amount < pending.amount:
            pending.note = f"Paid {tx.amount} of {pending.amount}; needs staff."
            pending.save(update_fields=["note", "updated_at"])
            return
        complete(pending, reference=tx.mpesa_receipt)
        return
    sub = Subscription.objects.select_related("plan").filter(account_number__iexact=(tx.account_reference or "").strip()).first()
    if sub is None or SubscriptionPayment.objects.filter(mpesa_transaction=tx).exists():
        return
    p = sub.plan if not sub.plan.is_free else None
    price = (p.price_yearly if sub.cycle == "yearly" else p.price_monthly) if p else ZERO
    periods = int(tx.amount // price) if price else 0
    payment = SubscriptionPayment.objects.create(
        subscription=sub, plan=sub.plan, cycle=sub.cycle, periods=max(periods, 1), list_price=tx.amount, amount=tx.amount, method="mpesa",
        status="pending", reference=tx.mpesa_receipt, mpesa_transaction=tx, paid_at=tx.paid_at,
        note="" if periods else "Paid straight to the paybill but less than one period, or on the free plan; needs staff.",
    )
    if periods:
        complete(payment, reference=tx.mpesa_receipt)


@transaction.atomic
def record_manual(sub: Subscription, p, *, cycle: str, periods: int, amount, method: str, reference: str = "", note: str = "", staff=None):
    """MannaBooks staff record a bank transfer, cash, or a credit (amount 0) that extends the subscription."""
    from apps.subscriptionpayments.models import SubscriptionPayment

    if periods < 1:
        raise BusinessRuleError("Pay for at least one period.")
    payment = SubscriptionPayment.objects.create(
        subscription=sub, plan=p, cycle=cycle, periods=periods, list_price=amount, amount=amount, method=method, status="pending",
        reference=reference, note=note, recorded_by=staff, paid_at=timezone.now(),
    )
    complete(payment, reference=reference)
    return payment


def move_to_free(sub: Subscription) -> Subscription:
    sub.plan, sub.status, sub.coupon, sub.coupon_payments_left = plan(FREE_PLAN), S.ACTIVE, None, None
    sub.save(update_fields=["plan", "status", "coupon", "coupon_payments_left", "updated_at"])
    return sub


def update_all(today: date | None = None) -> dict:
    """The daily pass: end trials, mark unpaid plans due, and make long-unpaid ones read-only."""
    today = today or timezone.localdate()
    counts = {"trial_ended": 0, "past_due": 0, "read_only": 0, "complimentary_ended": 0}
    for sub in Subscription.objects.select_related("plan", "workspace__owner").filter(complimentary=True, complimentary_until__lt=today):
        if getattr(sub.workspace.owner, "full_access", False):
            continue  # the owner's full access keeps it free
        end_complimentary(sub, today)
        sub.save()
        counts["complimentary_ended"] += 1
    for sub in Subscription.objects.select_related("plan").filter(complimentary=False).exclude(status=S.CANCELLED):
        paid = sub.paid_until is not None and sub.paid_until >= today
        if sub.status == S.TRIALING and sub.trial_ends_on and sub.trial_ends_on < today:
            if paid:
                sub.status = S.ACTIVE
                sub.save(update_fields=["status", "updated_at"])
            else:
                move_to_free(sub)
            counts["trial_ended"] += 1
        elif sub.status == S.ACTIVE and not sub.plan.is_free and not paid:
            sub.status = S.PAST_DUE
            sub.save(update_fields=["status", "updated_at"])
            counts["past_due"] += 1
        elif sub.status == S.PAST_DUE and sub.paid_until and sub.paid_until + timedelta(days=settings.GRACE_DAYS) < today:
            sub.status = S.READ_ONLY
            sub.save(update_fields=["status", "updated_at"])
            counts["read_only"] += 1
    from .reminders import send_due

    counts["reminders"] = send_due(today)
    return counts
