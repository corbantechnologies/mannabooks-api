"""The fixed asset register: add assets, depreciate them monthly, and record their sale or scrapping."""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2
from apps.journals.services import LineInput, replace_for_source
from apps.ledgeraccounts.services import system_account
from apps.sequences.services import next_value

from .models import FixedAsset

A = FixedAsset
# category: (method, useful life in years, reducing-balance rate, usual asset account code)
CATEGORY_DEFAULTS = {
    A.Category.LAND: (A.Method.NONE, 0, 0, "1500"),
    A.Category.BUILDINGS: (A.Method.STRAIGHT_LINE, 40, 0, "1500"),
    A.Category.MOTOR_VEHICLES: (A.Method.REDUCING_BALANCE, 0, 25, "1510"),
    A.Category.FURNITURE: (A.Method.STRAIGHT_LINE, 8, 0, "1500"),
    A.Category.COMPUTERS: (A.Method.STRAIGHT_LINE, 3, 0, "1520"),
    A.Category.PLANT: (A.Method.REDUCING_BALANCE, 0, 12.5, "1520"),
    A.Category.OFFICE_EQUIPMENT: (A.Method.STRAIGHT_LINE, 5, 0, "1520"),
    A.Category.OTHER: (A.Method.STRAIGHT_LINE, 5, 0, "1520"),
}
FINANCIAL = ("asset_account", "accumulated_account", "expense_account", "acquisition", "purchase_date", "in_service_date", "cost",
             "residual_value", "method", "useful_life_months", "rate_percent", "opening_accumulated", "depreciated_to")


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def next_month_end(d: date) -> date:
    return month_end(d + timedelta(days=1))


def charge(asset: FixedAsset, book_value) -> Decimal:
    """One month's depreciation on what is left of the asset."""
    if asset.method == A.Method.NONE or book_value <= asset.residual_value:
        return ZERO
    if asset.method == A.Method.STRAIGHT_LINE:
        amount = (asset.cost - asset.residual_value) / max(asset.useful_life_months, 1)
    else:
        amount = book_value * asset.rate_percent / 100 / 12
    return min(q2(amount), book_value - asset.residual_value)


def due_months(asset: FixedAsset, through: date) -> list[date]:
    """Month ends not yet depreciated, up to `through`."""
    if asset.status != A.Status.ACTIVE or asset.method == A.Method.NONE:
        return []
    m = next_month_end(asset.depreciated_to) if asset.depreciated_to else month_end(asset.in_service_date)
    out = []
    while m <= through:
        out.append(m)
        m = next_month_end(m)
    return out


def _check(asset: FixedAsset) -> None:
    if asset.cost <= 0:
        raise BusinessRuleError("Enter what the asset cost.")
    if asset.residual_value < 0 or asset.residual_value >= asset.cost:
        raise BusinessRuleError("The residual value must be less than the cost.")
    if asset.in_service_date < asset.purchase_date:
        raise BusinessRuleError("It can't be in use before it was bought.")
    if asset.asset_account.subtype != "fixed_asset" or asset.asset_account.system_key == "accumulated_depreciation":
        raise BusinessRuleError("Choose a fixed asset account for the cost (such as Motor vehicles).")
    if asset.accumulated_account.subtype != "fixed_asset":
        raise BusinessRuleError("The accumulated depreciation account must be a fixed asset account.")
    if asset.expense_account.account_type != "expense":
        raise BusinessRuleError("Depreciation must go to an expense account.")
    if asset.method == A.Method.STRAIGHT_LINE and asset.useful_life_months <= 0:
        raise BusinessRuleError("Enter the useful life.")
    if asset.method == A.Method.REDUCING_BALANCE and not (0 < asset.rate_percent <= 100):
        raise BusinessRuleError("Enter the yearly depreciation rate.")
    if asset.acquisition == A.Acquisition.EXISTING:
        if asset.opening_accumulated < 0 or asset.opening_accumulated > asset.cost - asset.residual_value:
            raise BusinessRuleError("Depreciation already charged can't be more than the cost less the residual value.")
        if asset.opening_accumulated and not asset.depreciated_to:
            raise BusinessRuleError("Say up to which month the earlier depreciation was charged.")
    else:
        asset.opening_accumulated = ZERO
        asset.depreciated_to = None
    if asset.depreciated_to:
        asset.depreciated_to = month_end(asset.depreciated_to)


def _post_opening(asset: FixedAsset, user=None) -> None:
    """An asset owned before MannaBooks goes into the books against opening balance equity."""
    lines = []
    if asset.acquisition == A.Acquisition.EXISTING:
        equity, label = system_account(asset.workspace, "opening_balance_equity"), f"{asset.number} {asset.name}"
        lines = [LineInput(account=asset.asset_account, debit=asset.cost, description=label), LineInput(account=equity, credit=asset.cost, description=label)]
        if asset.opening_accumulated:
            lines += [LineInput(account=equity, debit=asset.opening_accumulated, description=f"{label} depreciation to date"),
                      LineInput(account=asset.accumulated_account, credit=asset.opening_accumulated, description=f"{label} depreciation to date")]
    from apps.periods.models import AccountingPeriod

    first_open = AccountingPeriod.objects.filter(workspace=asset.workspace, status="open").order_by("start_date").values_list("start_date", flat=True).first()
    on = max(asset.purchase_date, first_open) if first_open else asset.purchase_date  # bought years ago: brought in when the books start
    replace_for_source(asset.workspace, source="asset_opening", source_model="fixedassets.FixedAsset.opening", source_id=str(asset.pk),
                       entry_date=on, description=f"Fixed asset brought in: {asset.number} {asset.name}", reference=asset.number,
                       lines=lines, user=user, dimensions=(None, None))


def defaults_for(workspace, category: str) -> dict:
    method, years, rate, code = CATEGORY_DEFAULTS.get(category, CATEGORY_DEFAULTS[A.Category.OTHER])
    from apps.ledgeraccounts.models import LedgerAccount

    return {"method": method, "useful_life_months": years * 12, "rate_percent": Decimal(str(rate)),
            "asset_account": LedgerAccount.objects.filter(workspace=workspace, code=code).first(),
            "accumulated_account": system_account(workspace, "accumulated_depreciation"), "expense_account": system_account(workspace, "depreciation")}


@transaction.atomic
def save(workspace, *, data: dict, user=None, asset: FixedAsset | None = None) -> FixedAsset:
    if asset is None:
        defaults = defaults_for(workspace, data.get("category") or A.Category.OTHER)
        for key, value in defaults.items():
            if data.get(key) is None:
                data[key] = value
        if data.get("asset_account") is None:
            raise BusinessRuleError("Choose the fixed asset account for the cost.")
        asset = FixedAsset(workspace=workspace, created_by=user, number=next_value(workspace, "fixed_asset"))
        data.setdefault("in_service_date", data.get("purchase_date"))
    else:
        locked = asset.depreciation_entries.exists() or asset.status == A.Status.DISPOSED
        changed = [k for k in FINANCIAL if k in data and data[k] != getattr(asset, k)]
        if locked and changed:
            raise BusinessRuleError("Depreciation has been charged on this asset, so its cost, dates and method can't change. "
                                    "Undo the depreciation runs first.")
    for key, value in data.items():
        setattr(asset, key, value)
    _check(asset)
    charged = ZERO if asset._state.adding else (asset.depreciation_entries.aggregate(s=Sum("amount"))["s"] or ZERO)
    asset.accumulated_depreciation = asset.opening_accumulated + charged
    if asset.status != A.Status.DISPOSED:
        asset.status = A.Status.FULLY_DEPRECIATED if asset.method != A.Method.NONE and asset.book_value <= asset.residual_value else A.Status.ACTIVE
    asset.save()
    _post_opening(asset, user)
    return asset


@transaction.atomic
def delete(asset: FixedAsset, user=None) -> None:
    if asset.depreciation_entries.exists() or asset.status == A.Status.DISPOSED:
        raise BusinessRuleError("This asset has depreciation or a disposal recorded. Undo those first.")
    asset.acquisition = A.Acquisition.RECORDED
    _post_opening(asset, user)
    asset.delete()


@transaction.atomic
def dispose(asset: FixedAsset, *, on: date, proceeds=ZERO, received_into=None, user=None) -> FixedAsset:
    asset = FixedAsset.objects.select_for_update().get(pk=asset.pk)
    if asset.status == A.Status.DISPOSED:
        raise BusinessRuleError("This asset is already disposed of.")
    if on < asset.purchase_date:
        raise BusinessRuleError("It can't be disposed of before it was bought.")
    previous = month_end(on.replace(day=1) - timedelta(days=1))
    if asset.method != A.Method.NONE and month_end(asset.in_service_date) <= previous and (asset.depreciated_to or date.min) < previous:
        raise BusinessRuleError(f"Run depreciation up to {previous:%B %Y} first, so the book value is up to date.")
    proceeds = q2(Decimal(str(proceeds or 0)))
    if proceeds > 0 and received_into is None:
        raise BusinessRuleError("Choose the account the money was received into.")
    gain = proceeds - asset.book_value
    label = f"Disposal of {asset.number} {asset.name}"
    lines = [LineInput(account=asset.asset_account, credit=asset.cost, description=label)]
    if asset.accumulated_depreciation:
        lines.append(LineInput(account=asset.accumulated_account, debit=asset.accumulated_depreciation, description=label))
    if proceeds:
        lines.append(LineInput(account=received_into.ledger_account, debit=proceeds, description=label))
    if gain:
        account = system_account(asset.workspace, "asset_disposal")
        lines.append(LineInput(account=account, credit=gain, description=label) if gain > 0 else LineInput(account=account, debit=-gain, description=label))
    replace_for_source(asset.workspace, source="asset_disposal", source_model="fixedassets.FixedAsset.disposal", source_id=str(asset.pk), entry_date=on,
                       description=label, reference=asset.number, lines=lines, user=user, dimensions=(asset.cost_center, None))
    asset.status, asset.disposal_date, asset.disposal_proceeds = A.Status.DISPOSED, on, proceeds
    asset.disposal_account, asset.disposal_gain = received_into, gain
    asset.save(update_fields=["status", "disposal_date", "disposal_proceeds", "disposal_account", "disposal_gain", "updated_at"])
    return asset


@transaction.atomic
def undo_disposal(asset: FixedAsset, user=None) -> FixedAsset:
    if asset.status != A.Status.DISPOSED:
        raise BusinessRuleError("This asset hasn't been disposed of.")
    replace_for_source(asset.workspace, source="asset_disposal", source_model="fixedassets.FixedAsset.disposal", source_id=str(asset.pk),
                       entry_date=asset.disposal_date, description="", lines=[], user=user)
    asset.status = A.Status.FULLY_DEPRECIATED if asset.method != A.Method.NONE and asset.book_value <= asset.residual_value else A.Status.ACTIVE
    asset.disposal_date, asset.disposal_proceeds, asset.disposal_account, asset.disposal_gain = None, ZERO, None, ZERO
    asset.save(update_fields=["status", "disposal_date", "disposal_proceeds", "disposal_account", "disposal_gain", "updated_at"])
    return asset


def schedule(asset: FixedAsset, years: int = 10) -> list[dict]:
    """The next years of depreciation, year by year, if nothing changes."""
    out, book = [], asset.book_value
    if asset.status != A.Status.ACTIVE or asset.method == A.Method.NONE:
        return out
    m = next_month_end(asset.depreciated_to) if asset.depreciated_to else month_end(asset.in_service_date)
    current = None
    for _ in range(years * 12):
        amount = charge(asset, book)
        if amount <= 0:
            break
        if current is None or current["year"] != m.year:
            current = {"year": m.year, "opening": book, "depreciation": ZERO, "closing": book}
            out.append(current)
        book -= amount
        current["depreciation"] += amount
        current["closing"] = book
        m = next_month_end(m)
    return out
