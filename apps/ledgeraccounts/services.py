from apps.core.exceptions import BusinessRuleError

from .chart import DEFAULT_CHART
from .models import LedgerAccount


def seed_chart(workspace, user=None) -> None:
    """Add the starting chart's accounts that the workspace doesn't have yet (one insert)."""
    existing = set(LedgerAccount.objects.filter(workspace=workspace).values_list("code", flat=True))
    LedgerAccount.objects.bulk_create(
        LedgerAccount(workspace=workspace, code=code, name=name, account_type=account_type, subtype=subtype,
                      system_key=key, description=description, created_by=user)
        for code, name, account_type, subtype, key, description in DEFAULT_CHART
        if code not in existing
    )


def system_account(workspace, key: str) -> LedgerAccount:
    """The account MannaBooks posts to for `key` (e.g. "sales", "vat_output")."""
    account = LedgerAccount.objects.filter(workspace=workspace, system_key=key).first()
    if account is None:  # an account added to the starting chart after this workspace was created
        seed_chart(workspace)
        account = LedgerAccount.objects.filter(workspace=workspace, system_key=key).first()
    if account is None:
        raise BusinessRuleError(f"The chart of accounts has no account for '{key}'. Restore it in the chart of accounts.")
    if not account.is_active:
        raise BusinessRuleError(f"The account {account} is inactive. Reactivate it to continue.")
    return account
