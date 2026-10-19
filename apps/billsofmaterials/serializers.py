from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.products.models import Product

from .models import BillOfMaterials, BillOfMaterialsLine


class ComponentSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    component_id = WorkspaceRelatedField(Product, source="component")
    component_name = serializers.CharField(source="component.name", read_only=True)
    unit = serializers.CharField(source="component.unit", read_only=True)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=4)


class BillOfMaterialsSerializer(serializers.ModelSerializer):
    product_id = WorkspaceRelatedField(Product, source="product")
    product_name = serializers.CharField(source="product.name", read_only=True)
    lines = ComponentSerializer(many=True)

    class Meta:
        model = BillOfMaterials
        fields = ["id", "product_id", "product_name", "name", "output_quantity", "notes", "is_active", "lines", "created_at"]
        read_only_fields = ["id", "product_name", "created_at"]

    def validate(self, attrs):
        product = attrs.get("product", getattr(self.instance, "product", None))
        if product is not None and not product.track_inventory:
            raise serializers.ValidationError({"product_id": ["The finished product must track stock."]})
        if attrs.get("output_quantity") is not None and attrs["output_quantity"] <= 0:
            raise serializers.ValidationError({"output_quantity": ["Must be more than zero."]})
        lines = attrs.get("lines")
        if lines is not None:
            if not lines:
                raise serializers.ValidationError({"lines": ["Add at least one component."]})
            for line in lines:
                if line["component"] == product:
                    raise serializers.ValidationError({"lines": ["A product can't be its own component."]})
                if not line["component"].track_inventory:
                    raise serializers.ValidationError({"lines": [f"{line['component']} must track stock to be used as a component."]})
                if line["quantity"] <= 0:
                    raise serializers.ValidationError({"lines": ["Component quantities must be more than zero."]})
        return attrs

    def _save_lines(self, bom, lines):
        if lines is None:
            return
        bom.lines.all().delete()
        BillOfMaterialsLine.objects.bulk_create(BillOfMaterialsLine(bom=bom, component=line["component"], quantity=line["quantity"]) for line in lines)

    def create(self, validated_data):
        lines = validated_data.pop("lines")
        bom = super().create(validated_data)
        self._save_lines(bom, lines)
        return bom

    def update(self, instance, validated_data):
        lines = validated_data.pop("lines", None)
        bom = super().update(instance, validated_data)
        self._save_lines(bom, lines)
        return bom
