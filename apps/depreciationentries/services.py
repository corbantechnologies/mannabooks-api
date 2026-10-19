"""Monthly depreciation runs. Each run posts one journal: depreciation expense (by account and cost centre) against accumulated depreciation."""
from collections import defaultdict
from datetime import date

from django.db import transaction
from django.db.models import Count, Sum

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO
from apps.fixedassets.models import FixedAsset
from apps.fixedassets.services import charge, due_months, month_end
from apps.journals.services import LineInput, replace_for_source

from .models import DepreciationEntry

SOURCE = {"source": "depreciation", "source_model": "depreciationentries.run"}


def preview(workspace, through: date) -> list[dict]:
    """What a run up to `through` would charge, asset by asset."""
    through = month_end(through)
    rows = []
    for asset in FixedAsset.objects.filter(workspace=workspace, status=FixedAsset.Status.ACTIVE, in_service_date__lte=through).select_related("cost_center"):
        book, total, months = asset.book_value, ZERO, 0
        for _ in due_months(asset, through):
            amount = charge(asset, book)
            if amount <= 0:
                break
            book -= amount
            total += amount
            months += 1
        if total:
            rows.append({"asset_id": asset.pk, "number": asset.number, "name": asset.name, "months": months, "amount": total, "book_value_after": book})
    return rows


def _post(workspace, run: date, user=None) -> None:
    entries = DepreciationEntry.objects.filter(workspace=workspace, run_month=run).select_related("asset__expense_account", "asset__accumulated_account",
                                                                                                "asset__cost_center")
    debit, credit = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for e in entries:
        debit[(e.asset.expense_account, e.asset.cost_center)] += e.amount
        credit[e.asset.accumulated_account] += e.amount
    label = f"Depreciation {run:%B %Y}"
    lines = [LineInput(account=a, debit=v, description=label, cost_center=cc) for (a, cc), v in debit.items() if v]
    lines += [LineInput(account=a, credit=v, description=label) for a, v in credit.items() if v]
    replace_for_source(workspace, **SOURCE, source_id=run.isoformat(), entry_date=run, description=label, reference=f"DEP-{run:%Y-%m}",
                       lines=lines if len(lines) >= 2 else [], user=user, dimensions=(None, None))


@transaction.atomic
def run(workspace, through: date, user=None) -> dict:
    """Depreciate every asset in use up to the end of `through`'s month (catching up months missed)."""
    through = month_end(through)
    later = DepreciationEntry.objects.filter(workspace=workspace, run_month__gt=through).exists()
    if later:
        raise BusinessRuleError("A later month has already been run. Undo it first.")
    count, total = 0, ZERO
    for asset in FixedAsset.objects.select_for_update().filter(workspace=workspace, status=FixedAsset.Status.ACTIVE, in_service_date__lte=through):
        for m in due_months(asset, through):
            amount = charge(asset, asset.book_value)
            if amount <= 0:
                break
            DepreciationEntry.objects.create(workspace=workspace, created_by=user, asset=asset, month_end=m, run_month=through, amount=amount,
                                             prior_depreciated_to=asset.depreciated_to)
            asset.accumulated_depreciation += amount
            asset.depreciated_to = m
            count += 1
            total += amount
        if asset.book_value <= asset.residual_value:
            asset.status = FixedAsset.Status.FULLY_DEPRECIATED
        asset.save(update_fields=["accumulated_depreciation", "depreciated_to", "status", "updated_at"])
    if not count:
        raise BusinessRuleError("Nothing to depreciate up to that month.")
    _post(workspace, through, user)
    return {"month": through, "entries": count, "total": total}


@transaction.atomic
def undo(workspace, run_month: date, user=None) -> None:
    run_month = month_end(run_month)
    if DepreciationEntry.objects.filter(workspace=workspace, run_month__gt=run_month).exists():
        raise BusinessRuleError("Undo the later runs first.")
    entries = list(DepreciationEntry.objects.filter(workspace=workspace, run_month=run_month).select_related("asset").order_by("month_end"))
    if not entries:
        raise BusinessRuleError("There is no depreciation run for that month.")
    if any(e.asset.status == FixedAsset.Status.DISPOSED for e in entries):
        raise BusinessRuleError("An asset in this run has since been disposed of. Undo the disposal first.")
    first = {}
    for e in entries:
        first.setdefault(e.asset_id, e)
    for asset_id, e in first.items():
        asset = FixedAsset.objects.select_for_update().get(pk=asset_id)
        removed = sum((x.amount for x in entries if x.asset_id == asset_id), ZERO)
        asset.accumulated_depreciation -= removed
        asset.depreciated_to = e.prior_depreciated_to
        asset.status = FixedAsset.Status.ACTIVE
        asset.save(update_fields=["accumulated_depreciation", "depreciated_to", "status", "updated_at"])
    DepreciationEntry.objects.filter(workspace=workspace, run_month=run_month).delete()
    _post(workspace, run_month, user)


def runs(workspace) -> list[dict]:
    rows = (DepreciationEntry.objects.filter(workspace=workspace).values("run_month")
            .annotate(total=Sum("amount"), entries=Count("id"), assets=Count("asset", distinct=True)).order_by("-run_month"))
    return [{"run_month": r["run_month"], "total": r["total"], "entries": r["entries"], "assets": r["assets"]} for r in rows]
