from django.utils import timezone
from rest_framework import serializers

from .models import Sequence


class SequenceSerializer(serializers.ModelSerializer):
    preview = serializers.SerializerMethodField()

    class Meta:
        model = Sequence
        fields = ["id", "key", "prefix", "next_number", "padding", "include_year", "preview"]
        read_only_fields = ["id", "key", "preview"]

    def get_preview(self, obj) -> str:
        return obj.format(obj.next_number, timezone.localdate().year)

    def validate_next_number(self, value):
        if self.instance and value < self.instance.next_number:
            raise serializers.ValidationError("The next number can only go up, so numbers are never reused.")
        return value
