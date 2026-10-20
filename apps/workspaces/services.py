from django.db import transaction
from django.utils.text import slugify

from apps.core.catalog import PRESET_ROLES

from .models import Workspace


def unique_slug(name: str) -> str:
    base = slugify(name)[:50] or "workspace"
    slug, n = base, 2
    while Workspace.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


@transaction.atomic
def create_workspace(user, **data) -> Workspace:
    """A new workspace with the preset roles, the creator as Owner and a head-office branch."""
    from apps.branches.models import Branch
    from apps.memberships.models import Membership
    from apps.roles.models import Role

    workspace = Workspace.objects.create(owner=user, slug=unique_slug(data["name"]), **data)
    created = Role.objects.bulk_create(
        Role(workspace=workspace, slug=spec["slug"], name=spec["name"], description=spec["description"],
             permissions=spec["permissions"], is_preset=True, created_by=user)
        for spec in PRESET_ROLES
    )
    roles = {role.slug: role for role in created}
    Membership.objects.create(
        workspace=workspace, user=user, role=roles["owner"], status=Membership.Status.ACTIVE, created_by=user
    )
    Branch.objects.create(workspace=workspace, name="Head office", code="HQ", is_default=True, created_by=user)
    seed_accounting(workspace, user)
    from apps.units.services import seed_units

    seed_units(workspace, user)
    from apps.subscriptions.services import start

    start(workspace)  # a trial of the top plan
    return workspace


def seed_accounting(workspace, user=None) -> None:
    """Currencies, the chart of accounts, tax rates and the current financial year."""
    from apps.currencies.services import seed_currencies
    from apps.fiscalyears.models import FiscalYear
    from apps.fiscalyears.services import create_initial_year
    from apps.ledgeraccounts.services import seed_chart
    from apps.taxrates.services import seed_tax_rates

    seed_currencies(workspace, user)
    seed_chart(workspace, user)
    seed_tax_rates(workspace, user)
    if not FiscalYear.objects.filter(workspace=workspace).exists():
        create_initial_year(workspace, user)


def workspaces_for(user):
    from apps.memberships.models import Membership

    return Workspace.objects.filter(
        is_active=True,
        memberships__user=user,
        memberships__status=Membership.Status.ACTIVE,
    ).distinct()
