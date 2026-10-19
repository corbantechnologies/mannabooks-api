from .models import Currency

COMMON = {
    "KES": ("Kenyan shilling", "KSh"),
    "USD": ("US dollar", "$"),
    "EUR": ("Euro", "EUR"),
    "GBP": ("Pound sterling", "GBP"),
    "UGX": ("Ugandan shilling", "USh"),
    "TZS": ("Tanzanian shilling", "TSh"),
    "RWF": ("Rwandan franc", "RF"),
}


def seed_currencies(workspace, user=None) -> None:
    base = (workspace.currency or "KES").upper()
    existing = set(Currency.objects.filter(workspace=workspace).values_list("code", flat=True))
    wanted = dict(COMMON)
    wanted.setdefault(base, (base, ""))
    Currency.objects.bulk_create(
        Currency(workspace=workspace, code=code, name=name, symbol=symbol, is_base=code == base,
                 is_active=code in (base, "USD"), created_by=user)
        for code, (name, symbol) in wanted.items()
        if code not in existing
    )


def base_currency(workspace) -> Currency:
    return Currency.objects.get(workspace=workspace, is_base=True)
