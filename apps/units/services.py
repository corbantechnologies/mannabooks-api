from .models import DEFAULT_UNITS, Unit


def seed_units(workspace, user=None) -> None:
    existing = set(Unit.objects.filter(workspace=workspace).values_list("abbreviation", flat=True))
    Unit.objects.bulk_create(
        Unit(workspace=workspace, name=name, abbreviation=abbr, etims_code=code, created_by=user)
        for name, abbr, code in DEFAULT_UNITS if abbr not in existing
    )
