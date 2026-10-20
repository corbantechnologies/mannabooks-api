from rest_framework import serializers


class RelatedDocumentSerializer(serializers.Serializer):
    kind = serializers.CharField()
    label = serializers.CharField()
    id = serializers.UUIDField()
    number = serializers.CharField()
    date = serializers.DateField()
    status = serializers.CharField(allow_blank=True)
    status_label = serializers.CharField(allow_blank=True)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    path = serializers.CharField()
    current = serializers.BooleanField()
