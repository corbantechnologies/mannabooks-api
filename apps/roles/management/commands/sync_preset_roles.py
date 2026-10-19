"""
Give every workspace's preset roles the permissions added in new releases. It only adds permissions:
anything a workspace removed from a preset role on purpose stays removed unless it is new in this release.
Runs on every deploy (see Procfile).
"""
from django.core.management.base import BaseCommand

from apps.core.catalog import PRESET_ROLES
from apps.roles.models import Role


class Command(BaseCommand):
    help = "Add newly released permissions to preset roles in every workspace."

    def handle(self, *args, **options):
        presets = {spec["slug"]: spec["permissions"] for spec in PRESET_ROLES}
        updated = 0
        for role in Role.objects.filter(is_preset=True, slug__in=presets.keys()):
            known = set(role.permissions)
            if "*" in known:
                continue
            missing = [code for code in presets[role.slug] if code not in known]
            if missing:
                role.permissions = sorted(known | set(missing))
                role.save(update_fields=["permissions", "updated_at"])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Preset roles updated: {updated}"))
