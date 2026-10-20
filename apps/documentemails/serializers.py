from rest_framework import serializers

from .models import DocumentEmail
from .registry import DOCS


class DocumentEmailSerializer(serializers.ModelSerializer):
    sent_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)

    class Meta:
        model = DocumentEmail
        fields = ["id", "document_type", "object_id", "document_number", "to", "cc", "subject", "message", "link", "status", "error",
                  "sent_at", "sent_by_name", "created_at"]
        read_only_fields = fields


class SendSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=list(DOCS))
    object_id = serializers.UUIDField()
    to = serializers.CharField(max_length=500)
    cc = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    subject = serializers.CharField(max_length=200)
    message = serializers.CharField(required=False, allow_blank=True, default="")


class DraftSerializer(serializers.Serializer):
    to = serializers.CharField(allow_blank=True)
    cc = serializers.CharField(allow_blank=True)
    subject = serializers.CharField()
    message = serializers.CharField()
