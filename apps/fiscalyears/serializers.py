from rest_framework import serializers

from .models import FiscalYear


class FiscalYearSerializer(serializers.ModelSerializer):
    closed_by_name = serializers.CharField(source="closed_by.full_name", read_only=True, default=None)
    open_periods = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = FiscalYear
        fields = ["id", "name", "start_date", "end_date", "status", "open_periods", "closed_at", "closed_by_name"]
        read_only_fields = fields


class FiscalYearCreateSerializer(serializers.Serializer):
    position = serializers.ChoiceField(choices=["next", "previous"], default="next")
