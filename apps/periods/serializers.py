from rest_framework import serializers

from .models import AccountingPeriod


class AccountingPeriodSerializer(serializers.ModelSerializer):
    fiscal_year_name = serializers.CharField(source="fiscal_year.name", read_only=True)
    closed_by_name = serializers.CharField(source="closed_by.full_name", read_only=True, default=None)

    class Meta:
        model = AccountingPeriod
        fields = ["id", "name", "fiscal_year", "fiscal_year_name", "start_date", "end_date", "status", "closed_at", "closed_by_name"]
        read_only_fields = fields
