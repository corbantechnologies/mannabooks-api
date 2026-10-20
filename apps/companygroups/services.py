"""
Company groups: who may see and change one, adding and removing companies, and the consolidated reports.

Consolidation adds up each company's profit and loss (or balance sheet) account by account, matched by account
code, then takes out what the companies did with each other: intercompany income and costs, and the balances in
"Due from / Due to group companies". What is left is the group's position with the outside world.
"""
from django.db.models import Q, Sum

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO

from .models import CompanyGroup

INTERCOMPANY_KEYS = ("due_from_group", "due_to_group")


def membership(user, workspace):
    from apps.memberships.models import Membership

    return Membership.objects.filter(user=user, workspace=workspace, status="active").select_related("role").first()


def companies(group: CompanyGroup) -> list:
    return list(group.workspaces.filter(is_active=True).order_by("name"))


def visible_groups(user):
    """Groups the person owns, or where they can see the reports of at least one company."""
    from apps.memberships.models import Membership

    mine = Q(owner=user)
    workspace_ids = [m.workspace_id for m in Membership.objects.filter(user=user, status="active").select_related("role") if m.has_perm("reports.view")]
    return CompanyGroup.objects.filter(mine | Q(workspaces__in=workspace_ids)).distinct()


def can_report(user, group) -> list[str]:
    """Companies whose reports this person can't see (empty: they may see the consolidated reports)."""
    missing = []
    for ws in companies(group):
        m = membership(user, ws)
        if not (m and m.has_perm("reports.view")):
            missing.append(ws.name)
    return missing


def require_owner(user, group):
    if group.owner_id != user.pk:
        raise BusinessRuleError("Only the group's owner can change it.")


def add_company(group, workspace, user):
    require_owner(user, group)
    m = membership(user, workspace)
    if not (m and m.has_perm("workspace.manage")):
        raise BusinessRuleError(f"You need to manage {workspace.name}'s settings to add it to a group.")
    if workspace.group_id and workspace.group_id != group.pk:
        raise BusinessRuleError(f"{workspace.name} is already in the group {workspace.group}. Remove it there first.")
    from apps.subscriptions.services import has_feature

    if not has_feature(workspace, "company_groups"):
        raise BusinessRuleError(f"{workspace.name}'s plan doesn't include company groups. Upgrade it in Settings > Plan and billing.")
    if workspace.currency != group.currency:
        raise BusinessRuleError(f"{workspace.name} keeps its books in {workspace.currency}; this group reports in {group.currency}.")
    workspace.group = group
    workspace.save(update_fields=["group", "updated_at"])
    return workspace


def remove_company(group, workspace, user):
    require_owner(user, group)
    if workspace.group_id != group.pk:
        raise BusinessRuleError(f"{workspace.name} isn't in this group.")
    if group.transactions.filter(Q(from_workspace=workspace) | Q(to_workspace=workspace), status="posted").exists():
        raise BusinessRuleError(f"{workspace.name} has intercompany transactions in this group. Void or settle them first.")
    workspace.group = None
    workspace.save(update_fields=["group", "updated_at"])


def _intercompany_pl(workspace, from_date, to_date) -> dict:
    """{account code: amount} of the company's income and costs that came from intercompany transactions."""
    from apps.journals.models import JournalLine

    rows = (JournalLine.objects.filter(entry__workspace=workspace, entry__source="intercompany", entry__entry_date__gte=from_date,
                                       entry__entry_date__lte=to_date, account__account_type__in=["income", "expense"])
            .exclude(entry__status="draft").values("account__code", "account__account_type").annotate(d=Sum("debit"), c=Sum("credit")))
    out = {}
    for r in rows:
        amount = (r["c"] or ZERO) - (r["d"] or ZERO) if r["account__account_type"] == "income" else (r["d"] or ZERO) - (r["c"] or ZERO)
        out[r["account__code"]] = out.get(r["account__code"], ZERO) + amount
    return out


def consolidated_profit_and_loss(group, *, from_date, to_date) -> dict:
    from apps.reports.services import PL_SECTIONS, profit_and_loss

    members = companies(group)
    sections = {key: {"key": key, "label": label, "rows": {}, "amounts": [ZERO] * len(members), "eliminations": ZERO, "total": ZERO}
                for key, label, _ in PL_SECTIONS}
    for i, ws in enumerate(members):
        pl = profit_and_loss(ws, from_date=from_date, to_date=to_date)
        ic = _intercompany_pl(ws, from_date, to_date)
        for sec in pl["sections"]:
            target = sections[sec["key"]]
            for row in sec["rows"]:
                line = target["rows"].setdefault(row["code"], {"code": row["code"], "name": row["name"], "amounts": [ZERO] * len(members),
                                                               "eliminations": ZERO, "total": ZERO})
                line["amounts"][i] += row["amount"]
                line["eliminations"] += ic.get(row["code"], ZERO)
                ic.pop(row["code"], None)
                target["amounts"][i] += row["amount"]
    out_sections = []
    for key, _, _ in PL_SECTIONS:
        sec = sections[key]
        rows = sorted(sec["rows"].values(), key=lambda r: r["code"])
        for r in rows:
            r["total"] = sum(r["amounts"], ZERO) - r["eliminations"]
        sec["eliminations"] = sum((r["eliminations"] for r in rows), ZERO)
        sec["total"] = sum(sec["amounts"], ZERO) - sec["eliminations"]
        out_sections.append({**sec, "rows": rows})
    by_key = {s["key"]: s for s in out_sections}

    def results(pick):
        gross = pick("income") - pick("cost_of_sales")
        operating = gross - pick("expense")
        return gross, operating, operating + pick("other_income") - pick("other_expense")

    gross, operating, net = results(lambda k: by_key[k]["total"])
    company_net = [results(lambda k, i=i: by_key[k]["amounts"][i])[2] for i in range(len(members))]
    return {
        "group": group.name, "currency": group.currency, "from_date": from_date, "to_date": to_date,
        "companies": [{"slug": ws.slug, "name": ws.name} for ws in members], "sections": out_sections,
        "gross_profit": gross, "operating_profit": operating, "net_profit": net, "company_net_profit": company_net,
        "eliminated_income": by_key["income"]["eliminations"] + by_key["other_income"]["eliminations"],
    }


def consolidated_balance_sheet(group, *, as_of) -> dict:
    from apps.ledgeraccounts.models import LedgerAccount
    from apps.reports.services import BS_GROUPS, balance_sheet

    members = companies(group)
    groups = {key: {"key": key, "label": label, "rows": {}, "amounts": [ZERO] * len(members), "eliminations": ZERO, "total": ZERO}
              for key, label, _, _ in BS_GROUPS}
    due_from = due_to = ZERO
    for i, ws in enumerate(members):
        intercompany_codes = set(LedgerAccount.objects.filter(workspace=ws, system_key__in=INTERCOMPANY_KEYS).values_list("code", flat=True))
        bs = balance_sheet(ws, as_of=as_of)
        for grp in bs["groups"]:
            target = groups[grp["key"]]
            for row in grp["rows"]:
                code = row["code"] or "profit"
                line = target["rows"].setdefault(code, {"code": row["code"], "name": row["name"], "amounts": [ZERO] * len(members),
                                                        "eliminations": ZERO, "total": ZERO})
                line["amounts"][i] += row["amount"]
                target["amounts"][i] += row["amount"]
                if row["code"] in intercompany_codes:
                    line["eliminations"] += row["amount"]
                    if grp["key"] == "current_assets":
                        due_from += row["amount"]
                    else:
                        due_to += row["amount"]
    out_groups = []
    for key, _, _, _ in BS_GROUPS:
        g = groups[key]
        rows = sorted(g["rows"].values(), key=lambda r: (r["code"] == "", r["code"]))
        for r in rows:
            r["total"] = sum(r["amounts"], ZERO) - r["eliminations"]
        g["eliminations"] = sum((r["eliminations"] for r in rows), ZERO)
        g["total"] = sum(g["amounts"], ZERO) - g["eliminations"]
        out_groups.append({**g, "rows": rows})
    by_key = {g["key"]: g for g in out_groups}
    assets = by_key["current_assets"]["total"] + by_key["fixed_assets"]["total"]
    liabilities = by_key["current_liabilities"]["total"] + by_key["long_term_liabilities"]["total"]
    equity = by_key["equity"]["total"]
    return {
        "group": group.name, "currency": group.currency, "as_of": as_of,
        "companies": [{"slug": ws.slug, "name": ws.name} for ws in members], "groups": out_groups,
        "total_assets": assets, "total_liabilities": liabilities, "total_equity": equity,
        # what the companies say they are owed by each other should equal what they say they owe; a gap means one side is missing
        "intercompany_difference": due_from - due_to,
        "balanced": assets == liabilities + equity,
    }
