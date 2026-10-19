from rest_framework import serializers

from .models import Unit


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "name", "abbreviation", "etims_code", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_abbreviation(self, value):
        value = value.strip()
        clash = Unit.objects.filter(workspace=self.context["workspace"], abbreviation__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Another unit uses this abbreviation.")
        return value
