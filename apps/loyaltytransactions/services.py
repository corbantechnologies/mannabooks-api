"""
Loyalty rules: earning on sales, redeeming at the till as a line discount, reversing on void, expiry and
tiers. Points are whole numbers; earning rounds down.
"""
import calendar
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2

from .models import LoyaltyTransaction

T = LoyaltyTransaction.Kind


def program_for(workspace):
    from apps.loyaltyprograms.models import LoyaltyProgram

    return LoyaltyProgram.objects.filter(workspace=workspace, is_active=True).first()


def member_for(customer):
    from apps.loyaltymembers.models import LoyaltyMember

    if customer is None:
        return None
    return LoyaltyMember.objects.select_for_update(of=("self",)).filter(customer=customer, is_active=True).select_related("tier").first()


def _add_months(d: date, months: int) -> date:
    i = d.month - 1 + months
    y, m = d.year + i // 12, i % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _refresh(member) -> None:
    """Recompute the balance and tier from the ledger."""
    from apps.loyaltytiers.models import LoyaltyTier

    txs = LoyaltyTransaction.objects.filter(member=member)
    member.points_balance = txs.aggregate(s=Sum("points"))["s"] or 0
    member.lifetime_points = txs.filter(kind=T.EARN).aggregate(s=Sum("points"))["s"] or 0
    year_ago = timezone.now() - timedelta(days=365)
    member.qualifying_points = txs.filter(kind=T.EARN, created_at__gte=year_ago).aggregate(s=Sum("points"))["s"] or 0
    member.tier = LoyaltyTier.objects.filter(workspace=member.workspace, min_points__lte=member.qualifying_points).order_by("-min_points").first()
    member.save(update_fields=["points_balance", "lifetime_points", "qualifying_points", "tier", "updated_at"])


def _credit(member, program, points, kind, document=None, doc_type="", description="") -> LoyaltyTransaction:
    expires = _add_months(timezone.localdate(), program.expiry_months) if program and program.expiry_months else None
    return LoyaltyTransaction.objects.create(
        workspace=member.workspace, member=member, kind=kind, points=points, remaining=points, expires_on=expires,
        document_type=doc_type, document_id=getattr(document, "pk", None), document_number=getattr(document, "number", "") or "",
        description=description,
    )


def _debit(member, points, kind, document=None, doc_type="", description="") -> LoyaltyTransaction:
    """Take points from the oldest unspent earnings first."""
    left = points
    for earn in LoyaltyTransaction.objects.select_for_update().filter(member=member, remaining__gt=0).order_by("expires_on", "created_at"):
        take = min(left, earn.remaining)
        earn.remaining -= take
        earn.save(update_fields=["remaining", "updated_at"])
        left -= take
        if not left:
            break
    return LoyaltyTransaction.objects.create(
        workspace=member.workspace, member=member, kind=kind, points=-points, document_type=doc_type,
        document_id=getattr(document, "pk", None), document_number=getattr(document, "number", "") or "", description=description,
    )


def points_for(program, member, net_amount) -> int:
    multiplier = member.tier.multiplier if member.tier else Decimal(1)
    return int((Decimal(net_amount) / program.spend_per_point * multiplier).to_integral_value(rounding=ROUND_DOWN))


def redemption_value(program, points: int) -> Decimal:
    return q2(points * program.point_value)


def discount_lines(workspace, customer, lines, prices_include_tax: bool, points: int):
    """
    Spread the value of `points` over the lines as fixed discounts (eTIMS dcAmt), in proportion to each
    line's total. Returns the lines; checks the member, balance and the programme's limits.
    """
    from apps.core.sales import price

    if not points:
        return lines
    program = program_for(workspace)
    if program is None:
        raise BusinessRuleError("The loyalty programme is switched off.")
    member = member_for(customer)
    if member is None:
        raise BusinessRuleError("Choose a customer who is a loyalty member to redeem points.")
    if points < program.min_redeem_points:
        raise BusinessRuleError(f"Redeem at least {program.min_redeem_points} points.")
    if points > member.points_balance:
        raise BusinessRuleError(f"{member.customer} has only {member.points_balance} points.")
    totals = [price(ln.quantity, ln.unit_price, ln.discount_percent, ln.tax_rate, prices_include_tax, ln.discount_amount)[2] for ln in lines]
    grand = sum(totals, ZERO)
    value = redemption_value(program, points)
    if value > q2(grand * program.max_redeem_percent / 100):
        raise BusinessRuleError(f"Points can pay for at most {program.max_redeem_percent}% of a sale ({q2(grand * program.max_redeem_percent / 100):,.2f}).")
    left = value
    for i, (line, total) in enumerate(zip(lines, totals, strict=True)):
        share = left if i == len(lines) - 1 else q2(value * total / grand) if grand else ZERO
        left -= share
        rate = line.tax_rate.rate / 100 if (line.tax_rate and line.tax_rate.kind == "vat" and not prices_include_tax) else ZERO
        line.discount_amount += q2(share / (1 + rate))
    return lines


@transaction.atomic
def after_sale(document, doc_type: str, redeemed_points: int = 0) -> None:
    """Record points redeemed on a sale, then the points it earns (on the amount after the discount, before VAT)."""
    program = program_for(document.workspace)
    customer = getattr(document, "customer", None)
    member = member_for(customer) if program else None
    if member is None:
        return
    if redeemed_points:
        _debit(member, redeemed_points, T.REDEEM, document, doc_type, f"Redeemed on {document.number}")
    if doc_type == "invoice" and not program.earn_on_invoices:
        _refresh(member)
        return
    earned = points_for(program, member, q2(document.subtotal * (document.exchange_rate or 1)))
    if earned > 0:
        _credit(member, program, earned, T.EARN, document, doc_type, f"Earned on {document.number}")
    _refresh(member)


@transaction.atomic
def reverse_document(document) -> None:
    """A voided sale gives back points it used and takes back points it earned (as far as they are unspent)."""
    txs = list(LoyaltyTransaction.objects.select_for_update().filter(document_id=document.pk, kind__in=[T.EARN, T.REDEEM]))
    if not txs:
        return
    member = txs[0].member
    program = program_for(document.workspace)
    for tx in txs:
        if tx.kind == T.EARN and tx.remaining:
            _debit_specific(tx, f"Reversed: {document.number} voided")
        elif tx.kind == T.REDEEM:
            _credit(member, program, -tx.points, T.REVERSE, document, tx.document_type, f"Returned: {document.number} voided")
    _refresh(member)


def _debit_specific(earn: LoyaltyTransaction, description: str, kind=T.REVERSE) -> None:
    points = earn.remaining
    earn.remaining = 0
    earn.save(update_fields=["remaining", "updated_at"])
    LoyaltyTransaction.objects.create(workspace=earn.workspace, member=earn.member, kind=kind, points=-points,
                                      document_type=earn.document_type, document_id=earn.document_id,
                                      document_number=earn.document_number, description=description)


@transaction.atomic
def adjust(member, points: int, reason: str, user=None) -> None:
    from apps.loyaltymembers.models import LoyaltyMember

    member = LoyaltyMember.objects.select_for_update().get(pk=member.pk)
    if points == 0:
        raise BusinessRuleError("Enter the points to add or remove.")
    if points > 0:
        _credit(member, program_for(member.workspace), points, T.ADJUST, description=reason)
    else:
        if -points > member.points_balance:
            raise BusinessRuleError(f"The member has only {member.points_balance} points.")
        _debit(member, -points, T.ADJUST, description=reason)
    _refresh(member)


def expire_due(today: date | None = None) -> int:
    """Expire unspent points past their date. Safe to run more than once a day."""
    today = today or timezone.localdate()
    members = set()
    for earn in LoyaltyTransaction.objects.filter(remaining__gt=0, expires_on__lt=today).select_related("member"):
        with transaction.atomic():
            _debit_specific(earn, f"Expired (earned {earn.created_at.date():%d %b %Y})", T.EXPIRE)
        members.add(earn.member)
    for member in members:
        _refresh(member)
    return len(members)


def regrade_all(workspace) -> None:
    from apps.loyaltymembers.models import LoyaltyMember

    for member in LoyaltyMember.objects.filter(workspace=workspace):
        _refresh(member)
