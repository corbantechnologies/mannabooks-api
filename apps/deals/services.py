from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO

from .models import Deal

S = Deal.Stage
CLOSED = (S.WON, S.LOST)


def move(deal: Deal, stage: str, *, lost_reason: str = "") -> Deal:
    """Move a deal along the pipeline. Won and lost close it (with the date); moving back reopens it."""
    if stage not in S.values:
        raise BusinessRuleError("Choose a pipeline stage.")
    if stage == S.LOST and not lost_reason.strip():
        raise BusinessRuleError("Say why the deal was lost, so the team can learn from it.")
    if stage == S.WON and deal.customer_id is None:
        raise BusinessRuleError("Choose the customer before marking the deal won.")
    deal.stage = stage
    deal.closed_at = timezone.localdate() if stage in CLOSED else None
    deal.lost_reason = lost_reason.strip()[:255] if stage == S.LOST else ""
    deal.save(update_fields=["stage", "closed_at", "lost_reason", "updated_at"])
    return deal


@transaction.atomic
def quotation_saved(deal: Deal, quotation) -> Deal:
    """A quotation made for the deal: link it and, if the deal was earlier in the pipeline, move it to Quote sent."""
    if quotation.workspace_id != deal.workspace_id:
        raise BusinessRuleError("That quotation belongs to another workspace.")
    deal.quotation = quotation
    deal.customer = deal.customer or quotation.customer
    if deal.stage in (S.PROSPECT, S.QUALIFIED):
        deal.stage = S.PROPOSAL
    deal.save(update_fields=["quotation", "customer", "stage", "updated_at"])
    return deal


def quotation_converted(quotation) -> None:
    """The customer took the quote: its open deals are won, at the quotation's value."""
    for deal in Deal.objects.filter(quotation=quotation).exclude(stage__in=CLOSED):
        deal.value = deal.value or quotation.subtotal
        deal.stage, deal.closed_at = S.WON, timezone.localdate()
        deal.save(update_fields=["value", "stage", "closed_at", "updated_at"])


def pipeline(workspace, deals=None) -> dict:
    """Per stage: how many deals, their value and their weighted value; plus what was won and lost this month."""
    deals = list(deals if deals is not None else Deal.objects.filter(workspace=workspace))
    stages = []
    for key, label in S.choices:
        rows = [d for d in deals if d.stage == key]
        stages.append({"stage": key, "label": label, "count": len(rows), "value": sum((d.value for d in rows), ZERO),
                       "weighted": sum((d.weighted_value for d in rows), ZERO), "probability": Deal.STAGE_PROBABILITY[key]})
    start = timezone.localdate().replace(day=1)
    won = [d for d in deals if d.stage == S.WON and d.closed_at and d.closed_at >= start]
    lost = [d for d in deals if d.stage == S.LOST and d.closed_at and d.closed_at >= start]
    open_deals = [d for d in deals if d.stage not in CLOSED]
    closed = len(won) + len(lost)
    return {
        "stages": stages,
        "open_value": sum((d.value for d in open_deals), ZERO),
        "weighted_value": sum((d.weighted_value for d in open_deals), ZERO),
        "won_this_month": sum((d.value for d in won), ZERO),
        "win_rate": (Decimal(len(won)) / closed * 100).quantize(Decimal("0.1")) if closed else None,
    }
