from rest_framework import generics
from rest_framework.permissions import AllowAny

from apps.subscriptions.serializers import PlanSerializer

from .models import Plan


class PublicPlanListView(generics.ListAPIView):
    """The plans and prices for the public pricing page."""

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PlanSerializer
    pagination_class = None
    queryset = Plan.objects.filter(is_active=True, is_public=True)
