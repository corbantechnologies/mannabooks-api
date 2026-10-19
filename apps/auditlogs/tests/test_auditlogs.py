import pytest

pytestmark = pytest.mark.django_db


def test_changes_are_recorded_with_a_diff(workspace, owner, client_for):
    api = client_for(owner)
    branch = api.post(f"/api/v1/w/{workspace.slug}/branches/", {"name": "Mombasa", "code": "msa"}, format="json").data
    assert branch["code"] == "MSA"
    api.patch(f"/api/v1/w/{workspace.slug}/branches/{branch['id']}/", {"name": "Mombasa CBD"}, format="json")
    logs = api.get(f"/api/v1/w/{workspace.slug}/audit-logs/", {"object_id": branch["id"]}).data["results"]
    assert [log["action"] for log in logs] == ["update", "create"]
    assert logs[0]["changes"] == {"name": {"from": "Mombasa", "to": "Mombasa CBD"}}


def test_sequences_only_go_up(workspace, owner, client_for):
    from apps.sequences.services import next_value

    assert next_value(workspace, "employee") == "EMP-0001"
    api = client_for(owner)
    seq = api.get(f"/api/v1/w/{workspace.slug}/sequences/").data["results"][0]
    assert seq["preview"] == "EMP-0002"
    down = api.patch(f"/api/v1/w/{workspace.slug}/sequences/{seq['id']}/", {"next_number": 1}, format="json")
    assert down.status_code == 400
