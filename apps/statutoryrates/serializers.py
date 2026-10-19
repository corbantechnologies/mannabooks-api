from rest_framework import serializers

from .models import StatutoryRate


class StatutoryRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatutoryRate
        fields = ["id", "effective_from", "paye_bands", "personal_relief", "shif_rate", "shif_minimum", "nssf_rate", "nssf_lower_limit",
                  "nssf_upper_limit", "housing_levy_rate", "deductions_before_paye", "notes", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_paye_bands(self, bands):
        if not isinstance(bands, list) or not bands or bands[-1].get("upto") is not None:
            raise serializers.ValidationError("List the bands from lowest; the last has no upper limit (upto: null).")
        previous = 0
        for band in bands[:-1]:
            if not isinstance(band.get("upto"), (int, float)) or band["upto"] <= previous:
                raise serializers.ValidationError("Each band's upper limit must be above the one before.")
            previous = band["upto"]
        for band in bands:
            if not isinstance(band.get("rate"), (int, float)) or not 0 <= band["rate"] <= 100:
                raise serializers.ValidationError("Rates are percentages from 0 to 100.")
        return bands
