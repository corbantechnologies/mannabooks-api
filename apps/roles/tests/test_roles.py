import pytest

pytestmark = pytest.mark.django_db


def test_custom_role_with_valid_permissions(workspace, owner, client_for):
    api = client_for(owner)
    url = f"/api/v1/w/{workspace.slug}/roles/"
    bad = api.post(url, {"name": "Supervisor", "permissions": ["employees.view", "nonsense.do"]}, format="json")
    assert bad.status_code == 400 and "permissions" in bad.data["errors"]
    ok = api.post(url, {"name": "Supervisor", "permissions": ["employees.view", "branches.*"]}, format="json")
    assert ok.status_code == 201 and ok.data["slug"] == "supervisor"


def test_preset_roles_cannot_be_deleted(workspace, owner, client_for):
    api = client_for(owner)
    roles = api.get(f"/api/v1/w/{workspace.slug}/roles/").data["results"]
    cashier = next(r for r in roles if r["slug"] == "cashier")
    res = api.delete(f"/api/v1/w/{workspace.slug}/roles/{cashier['id']}/")
    assert res.status_code == 409 and res.data["code"] == "rule"


def test_permissions_are_enforced(workspace, add_member, client_for):
    staff = client_for(add_member(workspace, "staff@example.com", "self-service"))
    res = staff.post(f"/api/v1/w/{workspace.slug}/branches/", {"name": "Mombasa", "code": "MSA"}, format="json")
    assert res.status_code == 403 and res.data["code"] == "permission_denied"
    assert staff.get(f"/api/v1/w/{workspace.slug}/roles/").status_code == 403


def test_permission_catalog(workspace, owner, client_for):
    res = client_for(owner).get(f"/api/v1/w/{workspace.slug}/roles/permissions/")
    assert any(m["module"] == "employees" for m in res.data["modules"])
    assert "inventory" in res.data["department_modules"]
