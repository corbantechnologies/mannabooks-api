from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField

from .models import ProductCategory


class ProductCategorySerializer(serializers.ModelSerializer):
    parent_id = WorkspaceRelatedField(ProductCategory, source="parent", allow_null=True, required=False)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)
    product_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ProductCategory
        fields = ["id", "name", "parent_id", "parent_name", "description", "is_active", "product_count", "created_at"]
        read_only_fields = ["id", "parent_name", "product_count", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        clash = ProductCategory.objects.filter(workspace=self.context["workspace"], name__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("There is already a category with this name.")
        return value

    def validate(self, attrs):
        parent = attrs.get("parent")
        node = parent
        while node is not None:
            if self.instance and node.pk == self.instance.pk:
                raise serializers.ValidationError({"parent_id": ["A category can't sit inside itself."]})
            node = node.parent
        return attrs
