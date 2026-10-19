import pytest


@pytest.fixture
def api():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def make_user(db):
    from apps.accounts.models import User

    def make(email="owner@example.com", password="S3cure-pass!", full_name="Owner Person"):
        return User.objects.create_user(email=email, password=password, full_name=full_name)

    return make


@pytest.fixture
def owner(make_user):
    return make_user()


@pytest.fixture
def workspace(owner):
    from apps.workspaces.services import create_workspace

    return create_workspace(owner, name="Acme Traders", currency="KES")


@pytest.fixture
def client_for():
    """An API client signed in as `user`."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    def make(user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return client

    return make


@pytest.fixture
def add_member(make_user):
    """Add a user to a workspace with a preset role."""
    from apps.memberships.models import Membership
    from apps.roles.models import Role

    def add(workspace, email, role_slug):
        user = make_user(email=email, full_name=email.split("@")[0].title())
        role = Role.objects.get(workspace=workspace, slug=role_slug)
        Membership.objects.create(workspace=workspace, user=user, role=role)
        return user

    return add
