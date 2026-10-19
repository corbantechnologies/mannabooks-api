from rest_framework import serializers

from apps.memberships.models import Membership
from apps.roles.models import Role

from .models import LEVEL_KINDS, ApprovalRule


class ApprovalLevelSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=list(LEVEL_KINDS))
    role_id = serializers.UUIDField(required=False, allow_null=True)
    membership_id = serializers.UUIDField(required=False, allow_null=True)
    label = serializers.CharField(read_only=True)


def level_label(workspace, level: dict) -> str:
    from apps.approvalrequests.registry import module_label

    kind = level.get("kind")
    if kind == "role":
        role = Role.objects.filter(workspace=workspace, pk=level.get("role_id")).first()
        return f"Anyone with the {role.name if role else 'deleted'} role"
    if kind == "member":
        m = Membership.objects.filter(workspace=workspace, pk=level.get("membership_id")).select_related("user").first()
        return m.user.full_name if m else "A removed member"
    if kind == "module_in_charge":
        return module_label(level.get("module", ""))
    return LEVEL_KINDS.get(kind, kind)


class ApprovalRuleSerializer(serializers.ModelSerializer):
    levels = ApprovalLevelSerializer(many=True)

    class Meta:
        model = ApprovalRule
        fields = ["id", "name", "document_type", "min_amount", "max_amount", "levels", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["levels"] = [{**lvl, "label": level_label(instance.workspace, lvl)} for lvl in instance.levels]
        return data

    def validate_levels(self, levels):
        workspace = self.context["workspace"]
        if not levels:
            raise serializers.ValidationError("Add at least one level.")
        if len(levels) > 6:
            raise serializers.ValidationError("Six levels at most.")
        out = []
        for n, lvl in enumerate(levels, start=1):
            kind = lvl["kind"]
            item = {"kind": kind}
            if kind == "role":
                if not Role.objects.filter(workspace=workspace, pk=lvl.get("role_id")).exists():
                    raise serializers.ValidationError(f"Level {n}: choose a role.")
                item["role_id"] = str(lvl["role_id"])
            if kind == "member":
                if not Membership.objects.filter(workspace=workspace, pk=lvl.get("membership_id"), status="active").exists():
                    raise serializers.ValidationError(f"Level {n}: choose a team member.")
                item["membership_id"] = str(lvl["membership_id"])
            out.append(item)
        return out

    def validate(self, attrs):
        low = attrs.get("min_amount", getattr(self.instance, "min_amount", 0))
        high = attrs.get("max_amount", getattr(self.instance, "max_amount", None))
        if high is not None and high < low:
            raise serializers.ValidationError({"max_amount": "The upper limit can't be below the lower one."})
        return attrs
