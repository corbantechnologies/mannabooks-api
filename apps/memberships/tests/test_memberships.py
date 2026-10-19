import pytest

from apps.memberships.models import Membership
from apps.roles.models import Role

pytestmark = pytest.mark.django_db


def test_the_last_owner_stays(workspace, owner, client_for):
    api = client_for(owner)
    me = Membership.objects.get(workspace=workspace, user=owner)
    admin_role = Role.objects.get(workspace=workspace, slug="admin")
    res = api.patch(f"/api/v1/w/{workspace.slug}/members/{me.id}/", {"role_id": str(admin_role.id)}, format="json")
    assert res.status_code == 409
    assert api.delete(f"/api/v1/w/{workspace.slug}/members/{me.id}/").status_code == 409


def test_only_owners_hand_out_ownership(workspace, add_member, client_for):
    admin = add_member(workspace, "admin@example.com", "admin")
    clerk = add_member(workspace, "clerk@example.com", "sales")
    clerk_membership = Membership.objects.get(workspace=workspace, user=clerk)
    owner_role = Role.objects.get(workspace=workspace, slug="owner")
    res = client_for(admin).patch(
        f"/api/v1/w/{workspace.slug}/members/{clerk_membership.id}/", {"role_id": str(owner_role.id)}, format="json"
    )
    assert res.status_code == 409


def test_suspended_members_lose_access(workspace, owner, add_member, client_for):
    clerk = add_member(workspace, "clerk@example.com", "sales")
    membership = Membership.objects.get(workspace=workspace, user=clerk)
    client_for(owner).patch(f"/api/v1/w/{workspace.slug}/members/{membership.id}/", {"status": "suspended"}, format="json")
    assert client_for(clerk).get(f"/api/v1/w/{workspace.slug}/").status_code == 404
