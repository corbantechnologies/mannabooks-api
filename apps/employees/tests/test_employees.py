import pytest

pytestmark = pytest.mark.django_db


def create(api, slug, **data):
    return api.post(f"/api/v1/w/{slug}/employees/", {"first_name": "A", "last_name": "B", **data}, format="json")


def test_staff_numbers_and_reporting_lines(workspace, owner, client_for):
    api = client_for(owner)
    boss = create(api, workspace.slug, first_name="Mary").data
    clerk = create(api, workspace.slug, first_name="John", reports_to_id=boss["id"]).data
    assert (boss["staff_number"], clerk["staff_number"]) == ("EMP-0001", "EMP-0002")
    assert clerk["reports_to_name"].startswith("Mary")
    loop = api.patch(f"/api/v1/w/{workspace.slug}/employees/{boss['id']}/", {"reports_to_id": clerk["id"]}, format="json")
    assert loop.status_code == 400 and "reports_to_id" in loop.data["errors"]


def test_self_service_sees_only_their_record(workspace, owner, add_member, client_for):
    from apps.employees.models import Employee
    from apps.memberships.models import Membership

    api = client_for(owner)
    create(api, workspace.slug, first_name="Other")
    staff = add_member(workspace, "staff@example.com", "self-service")
    mine = create(api, workspace.slug, first_name="Me").data
    Employee.objects.filter(pk=mine["id"]).update(membership=Membership.objects.get(workspace=workspace, user=staff))
    listing = client_for(staff).get(f"/api/v1/w/{workspace.slug}/employees/")
    assert [e["id"] for e in listing.data["results"]] == [mine["id"]]
    assert client_for(staff).patch(f"/api/v1/w/{workspace.slug}/employees/{mine['id']}/", {"phone": "1"}, format="json").status_code == 403


def test_department_head_is_module_in_charge(workspace, owner, client_for):
    from apps.employees.models import Employee
    from apps.memberships.models import Membership

    api = client_for(owner)
    head = create(api, workspace.slug, first_name="Jane").data
    Employee.objects.filter(pk=head["id"]).update(membership=Membership.objects.get(workspace=workspace, user=owner))
    stores = api.post(
        f"/api/v1/w/{workspace.slug}/departments/",
        {"name": "Stores", "head_id": head["id"], "modules": ["inventory", "purchasing"]},
        format="json",
    )
    assert stores.status_code == 201 and stores.data["head_name"].startswith("Jane")
    clash = api.post(f"/api/v1/w/{workspace.slug}/departments/", {"name": "Procurement", "modules": ["purchasing"]}, format="json")
    assert clash.status_code == 400 and "modules" in clash.data["errors"]
    context = api.get(f"/api/v1/w/{workspace.slug}/context/").data
    assert context["in_charge_of"] == ["inventory", "purchasing"] and context["department"] is None
