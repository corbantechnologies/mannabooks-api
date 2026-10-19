from rest_framework import serializers

from .models import EtimsSubmission


class EtimsSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EtimsSubmission
        fields = ["id", "document_type", "document_id", "document_number", "kra_invoice_number", "status", "attempts",
                  "last_error", "signed_at", "created_at"]
        read_only_fields = fields
