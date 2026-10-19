from django.db.models import Count
from rest_framework import generics

from apps.core.exceptions import BusinessRuleError
from apps.core.tenancy import WorkspaceScopedMixin

from .models import ProductCategory
from .serializers import ProductCategorySerializer


class CategoryMixin(WorkspaceScopedMixin):
    module = "products"
    queryset = ProductCategory.objects.select_related("parent")
    serializer_class = ProductCategorySerializer

    def workspace_queryset(self):
        return super().workspace_queryset().annotate(product_count=Count("products")).order_by("name")


class ProductCategoryListCreateView(CategoryMixin, generics.ListCreateAPIView):
    filterset_fields = ["is_active", "parent"]
    search_fields = ["name"]


class ProductCategoryDetailView(CategoryMixin, generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ["get", "patch", "delete"]

    def perform_destroy(self, instance):
        if instance.products.exists() or instance.children.exists():
            raise BusinessRuleError("This category has products or sub-categories. Move them or deactivate it instead.")
        super().perform_destroy(instance)
