import pytest
from django.core import mail

from apps.employees.models import Employee
from apps.memberships.models import Membership
from apps.roles.models import Role

pytestmark = pytest.mark.django_db


def test_invite_preview_and_accept(workspace, owner, make_user, client_for, api, django_capture_on_commit_callbacks):
    sales = Role.objects.get(workspace=workspace, slug="sales")
    with django_capture_on_commit_callbacks(execute=True):
        res = client_for(owner).post(
            f"/api/v1/w/{workspace.slug}/invitations/", {"email": "Kim@Example.com", "role_id": str(sales.id)}, format="json"
        )
    assert res.status_code == 201 and res.data["email"] == "kim@example.com"
    assert len(mail.outbox) == 1 and "/invite/" in mail.outbox[0].body
    token = res.data["link"].rsplit("/", 1)[-1]

    preview = api.get(f"/api/v1/invitations/{token}/")
    assert preview.status_code == 200 and preview.data["workspace_name"] == "Acme Traders"

    wrong = client_for(make_user(email="someone@example.com"))
    assert wrong.post(f"/api/v1/invitations/{token}/accept/").status_code == 403

    kim = make_user(email="kim@example.com")
    accepted = client_for(kim).post(f"/api/v1/invitations/{token}/accept/")
    assert accepted.status_code == 200 and accepted.data["workspace_slug"] == workspace.slug
    assert Membership.objects.get(workspace=workspace, user=kim).role == sales
    assert client_for(kim).post(f"/api/v1/invitations/{token}/accept/").status_code == 409


def test_existing_members_are_not_invited(workspace, owner, client_for):
    sales = Role.objects.get(workspace=workspace, slug="sales")
    res = client_for(owner).post(
        f"/api/v1/w/{workspace.slug}/invitations/", {"email": owner.email, "role_id": str(sales.id)}, format="json"
    )
    assert res.status_code == 409


def test_employee_self_service_invitation(workspace, owner, make_user, client_for):
    api = client_for(owner)
    emp = api.post(
        f"/api/v1/w/{workspace.slug}/employees/",
        {"first_name": "Grace", "last_name": "Achieng", "email": "grace@example.com"},
        format="json",
    ).data
    invite = api.post(f"/api/v1/w/{workspace.slug}/employees/{emp['id']}/invite/", {}, format="json")
    assert invite.status_code == 201 and invite.data["role_name"] == "Self-service"
    grace = make_user(email="grace@example.com")
    token = invite.data["link"].rsplit("/", 1)[-1]
    client_for(grace).post(f"/api/v1/invitations/{token}/accept/")
    assert Employee.objects.get(pk=emp["id"]).membership.user == grace
