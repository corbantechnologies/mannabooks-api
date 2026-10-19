from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import EtimsSubmission
from .serializers import EtimsSubmissionSerializer


class EtimsSubmissionListView(WorkspaceScopedMixin, generics.ListAPIView):
    module = "etims"
    queryset = EtimsSubmission.objects.all()
    serializer_class = EtimsSubmissionSerializer
    filterset_fields = ["status", "document_type"]
    search_fields = ["document_number"]
