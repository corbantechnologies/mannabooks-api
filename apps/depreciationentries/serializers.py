from rest_framework import serializers

M = {"max_digits": 18, "decimal_places": 2}


class DepreciationRunSerializer(serializers.Serializer):
    run_month = serializers.DateField()
    total = serializers.DecimalField(**M)
    entries = serializers.IntegerField()
    assets = serializers.IntegerField()


class DepreciationPreviewSerializer(serializers.Serializer):
    asset_id = serializers.UUIDField()
    number = serializers.CharField()
    name = serializers.CharField()
    months = serializers.IntegerField()
    amount = serializers.DecimalField(**M)
    book_value_after = serializers.DecimalField(**M)


class RunRequestSerializer(serializers.Serializer):
    month = serializers.DateField(help_text="Any day in the last month to depreciate")


class RunResultSerializer(serializers.Serializer):
    month = serializers.DateField()
    entries = serializers.IntegerField()
    total = serializers.DecimalField(**M)
