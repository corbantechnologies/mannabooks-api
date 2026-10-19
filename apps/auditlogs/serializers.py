from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = ["id", "action", "model", "object_id", "object_repr", "changes", "actor_name", "ip_address", "created_at"]
        read_only_fields = fields
