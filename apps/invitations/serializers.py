from rest_framework import serializers

from apps.roles.models import Role

from .models import Invitation


class InvitationSerializer(serializers.ModelSerializer):
    role_id = serializers.PrimaryKeyRelatedField(source="role", queryset=Role.objects.none())
    role_name = serializers.CharField(source="role.name", read_only=True)
    employee_id = serializers.UUIDField(read_only=True, allow_null=True)
    invited_by = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    is_expired = serializers.BooleanField(read_only=True)
    link = serializers.CharField(read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id", "email", "role_id", "role_name", "employee_id", "status", "is_expired", "expires_at",
            "invited_by", "link", "created_at",
        ]
        read_only_fields = ["id", "role_name", "employee_id", "status", "is_expired", "expires_at", "invited_by", "link", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        workspace = self.context.get("workspace")
        if workspace is not None:
            self.fields["role_id"].queryset = Role.objects.filter(workspace=workspace)


class InvitationPreviewSerializer(serializers.Serializer):
    """What someone sees on the invitation link before signing in."""

    workspace_name = serializers.CharField(source="workspace.name")
    role_name = serializers.CharField(source="role.name")
    email = serializers.EmailField()
    status = serializers.CharField()
    is_expired = serializers.BooleanField()


class AcceptedInvitationSerializer(serializers.Serializer):
    workspace_slug = serializers.CharField()
    workspace_name = serializers.CharField()
