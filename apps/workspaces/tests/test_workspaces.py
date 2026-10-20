import pytest

from apps.branches.models import Branch
from apps.roles.models import Role

pytestmark = pytest.mark.django_db


def test_creating_a_workspace_sets_up_roles_owner_and_branch(owner, client_for):
    api = client_for(owner)
    res = api.post("/api/v1/workspaces/", {"name": "Acme Traders"}, format="json")
    assert res.status_code == 201 and res.data["slug"] == "acme-traders"
    slug = res.data["slug"]
    assert Role.objects.filter(workspace__slug=slug, is_preset=True).count() == 8
    assert Branch.objects.get(workspace__slug=slug).is_default
    listing = api.get("/api/v1/workspaces/")
    assert listing.data["results"][0]["role"] == "Owner"
    again = api.post("/api/v1/workspaces/", {"name": "Acme Traders"}, format="json")
    assert again.data["slug"] == "acme-traders-2"


def test_context_lists_permissions(workspace, owner, client_for):
    res = client_for(owner).get(f"/api/v1/w/{workspace.slug}/context/")
    assert res.status_code == 200
    assert res.data["is_owner"] and res.data["permissions"] == ["*"]


def test_outsiders_cannot_see_a_workspace(workspace, make_user, client_for):
    stranger = client_for(make_user(email="stranger@example.com"))
    assert stranger.get(f"/api/v1/w/{workspace.slug}/").status_code == 404
    assert stranger.get(f"/api/v1/w/{workspace.slug}/branches/").status_code == 404
    assert stranger.get("/api/v1/w/does-not-exist/").status_code == 404


def test_kra_pin_and_vat_rules(workspace, owner, client_for):
    api = client_for(owner)
    bad = api.patch(f"/api/v1/w/{workspace.slug}/", {"kra_pin": "123"}, format="json")
    assert bad.status_code == 400 and "kra_pin" in bad.data["errors"]
    vat = api.patch(f"/api/v1/w/{workspace.slug}/", {"vat_registered": True}, format="json")
    assert vat.status_code == 400
    ok = api.patch(f"/api/v1/w/{workspace.slug}/", {"kra_pin": "p051234567x", "vat_registered": True}, format="json")
    assert ok.status_code == 200 and ok.data["kra_pin"] == "P051234567X"


def test_kra_pin_shapes():
    import pytest
    from rest_framework.exceptions import ValidationError

    from apps.core.kra import clean_pin

    assert clean_pin("a123456789b") == "A123456789B"  # a person
    assert clean_pin(" P051234567X ") == "P051234567X"  # a company
    assert clean_pin("") == ""
    with pytest.raises(ValidationError, match="13 characters"):
        clean_pin("P05123456789Y")  # two digits too many
    with pytest.raises(ValidationError, match="start with A"):
        clean_pin("B123456789C")
    with pytest.raises(ValidationError):
        clean_pin("", required=True)


def test_only_the_owner_deletes(workspace, owner, add_member, client_for):
    admin = add_member(workspace, "admin@example.com", "admin")
    assert client_for(admin).delete(f"/api/v1/w/{workspace.slug}/").status_code == 409
    assert client_for(owner).delete(f"/api/v1/w/{workspace.slug}/").status_code == 204
    assert client_for(owner).get(f"/api/v1/w/{workspace.slug}/").status_code == 404


@pytest.mark.django_db
def test_registering_for_vat_makes_16_percent_the_default(workspace, owner, client_for):
    from apps.taxrates.models import TaxRate

    def default():
        return TaxRate.objects.get(workspace=workspace, is_default=True).code

    workspace.refresh_from_db()
    assert not workspace.vat_registered and default() == "NONVAT"
    api = client_for(owner)
    url = f"/api/v1/w/{workspace.slug}/"
    assert api.patch(url, {"vat_registered": True, "kra_pin": "P051234567X"}, format="json").status_code == 200
    assert default() == "VAT16"
    api.patch(url, {"vat_registered": False}, format="json")
    assert default() == "NONVAT"


def test_goal_switches_on_modules(workspace, owner, client_for):
    api = client_for(owner)
    url = f"/api/v1/w/{workspace.slug}/"
    assert api.get(url).data["modules"] == []  # empty: everything on, as for existing workspaces
    shop = api.patch(url, {"business_goal": "shop"}, format="json")
    assert shop.status_code == 200 and shop.data["modules"] == ["sales", "pos", "purchasing", "inventory", "banking"]
    picked = api.patch(url, {"modules": ["banking", "sales", "sales"]}, format="json").data
    assert picked["modules"] == ["sales", "banking"]
    assert api.patch(url, {"modules": ["spaceships"]}, format="json").status_code == 400
    context = api.get(f"/api/v1/w/{workspace.slug}/context/").data
    assert {m["key"] for m in context["module_catalog"]} >= {"sales", "people"} and context["goal_catalog"][0]["key"] == "invoicing"
