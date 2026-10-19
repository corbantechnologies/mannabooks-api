import re

import pytest
from django.core import mail

pytestmark = pytest.mark.django_db

PASSWORD = "S3cure-pass!"


def register(api, email="jane@example.com"):
    return api.post("/api/v1/auth/register/", {"email": email, "full_name": "Jane Wanjiru", "password": PASSWORD}, format="json")


def test_register_returns_tokens_and_user(api):
    res = register(api, "Jane@Example.com")
    assert res.status_code == 201
    assert res.data["access"] and res.data["refresh"]
    assert res.data["user"]["email"] == "jane@example.com"


def test_duplicate_email_uses_the_error_shape(api):
    register(api)
    res = register(api)
    assert res.status_code == 400
    assert res.data["code"] == "invalid" and "email" in res.data["errors"]


def test_login_and_me(api):
    register(api)
    bad = api.post("/api/v1/auth/login/", {"email": "jane@example.com", "password": "wrong"}, format="json")
    assert bad.status_code == 400 and bad.data["message"] == "Wrong email or password."
    ok = api.post("/api/v1/auth/login/", {"email": "jane@example.com", "password": PASSWORD}, format="json")
    assert ok.status_code == 200
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {ok.data['access']}")
    me = api.patch("/api/v1/auth/me/", {"phone": "0712345678"}, format="json")
    assert me.status_code == 200 and me.data["phone"] == "0712345678"


def test_logout_revokes_the_refresh_token(api):
    tokens = register(api).data
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert api.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}, format="json").status_code == 204
    api.credentials()
    assert api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code == 401


def test_google_sign_in_is_off_by_default(api):
    res = api.post("/api/v1/auth/google/", {"id_token": "x"}, format="json")
    assert res.status_code == 403 and "turned off" in res.data["message"]


def test_google_sign_in_creates_then_links(api, monkeypatch, make_user):
    from apps.accounts import services

    claims = {"sub": "g-123", "email": "amina@example.com", "email_verified": True, "name": "Amina Odhiambo"}
    monkeypatch.setattr(services, "verify_google_token", lambda token: claims)
    first = api.post("/api/v1/auth/google/", {"id_token": "x"}, format="json")
    assert first.status_code == 200 and first.data["user"]["full_name"] == "Amina Odhiambo"
    assert first.data["user"]["has_password"] is False

    existing = make_user(email="peter@example.com")
    claims.update(sub="g-456", email="peter@example.com")
    linked = api.post("/api/v1/auth/google/", {"id_token": "x"}, format="json")
    assert linked.data["user"]["id"] == str(existing.id)
    existing.refresh_from_db()
    assert existing.google_sub == "g-456" and existing.email_verified


def test_password_reset(api):
    register(api)
    assert api.post("/api/v1/auth/password/reset/", {"email": "nobody@example.com"}, format="json").status_code == 204
    assert len(mail.outbox) == 0  # unknown emails get the same answer and no mail
    api.post("/api/v1/auth/password/reset/", {"email": "jane@example.com"}, format="json")
    uid, token = re.search(r"uid=([^&]+)&token=(\S+)", mail.outbox[0].body).groups()
    res = api.post("/api/v1/auth/password/reset/confirm/", {"uid": uid, "token": token, "new_password": "An0ther-pass!"}, format="json")
    assert res.status_code == 204
    login = api.post("/api/v1/auth/login/", {"email": "jane@example.com", "password": "An0ther-pass!"}, format="json")
    assert login.status_code == 200


def test_a_refresh_token_works_for_parallel_refreshes(api):
    tokens = register(api).data
    first = api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
    second = api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert first.status_code == second.status_code == 200


def test_sign_up_with_a_business_name_creates_the_workspace(api):
    from apps.memberships.models import Membership

    res = api.post("/api/v1/auth/register/", {"email": "wanjiku@example.com", "full_name": "Wanjiku Kamau",
                                              "password": PASSWORD, "business_name": "Kamau Hardware"}, format="json")
    assert res.status_code == 201 and res.data["workspace_slug"] == "kamau-hardware"
    membership = Membership.objects.get(user__email="wanjiku@example.com")
    assert membership.workspace.name == "Kamau Hardware" and membership.is_owner


def test_sign_up_without_a_business_name_creates_no_workspace(api):
    from apps.memberships.models import Membership

    res = register(api, "invitee@example.com")
    assert res.data["workspace_slug"] is None
    assert not Membership.objects.filter(user__email="invitee@example.com").exists()
