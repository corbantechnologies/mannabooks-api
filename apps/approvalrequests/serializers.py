from rest_framework import serializers

from apps.approvalrules.serializers import level_label

from . import services
from .models import ApprovalRequest, ApprovalStep
from .registry import DOCS


class ApprovalStepSerializer(serializers.ModelSerializer):
    decided_by_name = serializers.CharField(source="decided_by.full_name", read_only=True, default=None)

    class Meta:
        model = ApprovalStep
        fields = ["id", "level", "decision", "decided_by_name", "comment", "created_at"]


class ApprovalRequestSerializer(serializers.ModelSerializer):
    document_label = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()
    requested_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    level_labels = serializers.SerializerMethodField()
    waiting_on = serializers.SerializerMethodField()
    can_decide = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    steps = ApprovalStepSerializer(many=True, read_only=True)

    class Meta:
        model = ApprovalRequest
        fields = ["id", "document_type", "document_label", "object_id", "document_number", "summary", "amount", "link", "status", "current_level",
                  "level_labels", "waiting_on", "can_decide", "can_cancel", "requested_by_name", "steps", "created_at", "decided_at"]

    def _user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_document_label(self, obj) -> str:
        return DOCS[obj.document_type].label if obj.document_type in DOCS else obj.document_type

    def get_link(self, obj) -> str:
        return DOCS[obj.document_type].path.format(id=obj.object_id) if obj.document_type in DOCS else ""

    def get_level_labels(self, obj) -> list[str]:
        return [level_label(obj.workspace, lvl) for lvl in obj.levels]

    def get_waiting_on(self, obj) -> list[str]:
        if obj.status != ApprovalRequest.Status.PENDING:
            return []
        return [m.user.full_name for m in services.approvers(obj)]

    def get_can_decide(self, obj) -> bool:
        user = self._user()
        return bool(user and services.can_decide(obj, user))

    def get_can_cancel(self, obj) -> bool:
        user = self._user()
        request = self.context.get("request")
        manage = bool(request and getattr(request, "membership", None) and request.membership.has_perm("approvals.manage"))
        return obj.status == ApprovalRequest.Status.PENDING and bool(user) and (obj.created_by_id == user.id or manage)


class SubmitSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=list(DOCS))
    object_id = serializers.UUIDField()


class DecideSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    comment = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ApprovalStatusSerializer(serializers.Serializer):
    required = serializers.BooleanField()
    rule_name = serializers.CharField(allow_null=True)
    levels = serializers.ListField(child=serializers.CharField())
    request = ApprovalRequestSerializer(allow_null=True)
    can_submit = serializers.BooleanField()
