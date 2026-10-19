from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.posregisters.models import PosRegister

from .models import PosShift
from .services import summary


class PosShiftSerializer(serializers.ModelSerializer):
    register_id = WorkspaceRelatedField(PosRegister, source="register")
    register_name = serializers.CharField(source="register.name", read_only=True)
    cashier_name = serializers.CharField(source="cashier.full_name", read_only=True)
    totals = serializers.SerializerMethodField()

    class Meta:
        model = PosShift
        fields = ["id", "number", "register_id", "register_name", "cashier_name", "status", "opened_at", "closed_at",
                  "opening_float", "expected_cash", "counted_cash", "cash_difference", "closing_notes", "totals"]
        read_only_fields = ["id", "number", "register_name", "cashier_name", "status", "opened_at", "closed_at", "expected_cash",
                            "counted_cash", "cash_difference", "closing_notes", "totals"]
        validators = []  # the one-open-shift rules are checked in services.open_shift with a clear message

    def get_totals(self, obj) -> dict:
        return summary(obj)


class CloseShiftSerializer(serializers.Serializer):
    counted_cash = serializers.DecimalField(max_digits=18, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)
