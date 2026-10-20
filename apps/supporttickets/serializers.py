from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from . import services
from .models import SupportTicket


class TicketMessageSerializer(serializers.Serializer):
    author_name = serializers.CharField()
    staff = serializers.BooleanField()
    internal = serializers.BooleanField(default=False)
    body = serializers.CharField()
    at = serializers.DateTimeField()


class SupportTicketSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()
    business = serializers.CharField(source="workspace.name", read_only=True, default=None)
    business_slug = serializers.CharField(source="workspace.slug", read_only=True, default=None)
    raised_by_name = serializers.CharField(source="raised_by.full_name", read_only=True)
    raised_by_email = serializers.CharField(source="raised_by.email", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True, default=None)

    class Meta:
        model = SupportTicket
        fields = ["id", "number", "business", "business_slug", "raised_by_name", "raised_by_email", "category", "subject", "status", "priority",
                  "assigned_to_name", "page", "messages", "last_reply_by_staff", "resolved_at", "created_at", "updated_at"]
        read_only_fields = fields

    @extend_schema_field(TicketMessageSerializer(many=True))
    def get_messages(self, obj):
        staff = bool(self.context.get("staff"))
        return TicketMessageSerializer(services.public_messages(obj, staff), many=True).data


class OpenTicketSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=SupportTicket.Category.choices)
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField(max_length=10000)
    page = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ReplySerializer(serializers.Serializer):
    body = serializers.CharField(max_length=10000)
    internal = serializers.BooleanField(default=False, help_text="Staff only: a note the customer doesn't see")
