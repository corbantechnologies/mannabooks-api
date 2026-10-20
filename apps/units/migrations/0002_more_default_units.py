from django.db import migrations

NEW = [("Carton", "ctn"), ("Crate", "crate"), ("Bottle", "btl"), ("Shot", "shot"), ("Tonne", "t")]


def add_units(apps, schema_editor):
    """Workspaces that already have units get the new defaults too (never a duplicate abbreviation)."""
    Unit = apps.get_model("units", "Unit")
    for workspace_id in Unit.objects.values_list("workspace_id", flat=True).distinct():
        have = set(Unit.objects.filter(workspace_id=workspace_id).values_list("abbreviation", flat=True))
        Unit.objects.bulk_create(Unit(workspace_id=workspace_id, name=name, abbreviation=abbr) for name, abbr in NEW if abbr not in have)


class Migration(migrations.Migration):
    dependencies = [("units", "0001_initial")]
    operations = [migrations.RunPython(add_units, migrations.RunPython.noop)]
