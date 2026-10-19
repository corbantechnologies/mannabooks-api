from rest_framework import generics

from apps.core.tenancy import WorkspaceScopedMixin

from .models import Sequence
from .serializers import SequenceSerializer


class SequenceMixin(WorkspaceScopedMixin):
    module = "sequences"
    queryset = Sequence.objects.all()
    serializer_class = SequenceSerializer


class SequenceListView(SequenceMixin, generics.ListAPIView):
    """Sequences are created the first time a module numbers something; here they are listed and tuned."""


class SequenceDetailView(SequenceMixin, generics.RetrieveUpdateAPIView):
    http_method_names = ["get", "patch"]
