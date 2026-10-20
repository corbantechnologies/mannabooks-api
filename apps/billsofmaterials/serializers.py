from drf_spectacular.utils import extend_schema_field
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
    unit_cost = serializers.SerializerMethodField(help_text="What one unit of the ingredient costs now")
    cost = serializers.SerializerMethodField(help_text="This ingredient's cost for one batch")

    def _row(self, line):
        return next((r for r in self.parent.parent._costing(line.bom)["lines"] if r["line_id"] == line.pk), {})

    def get_unit_cost(self, line) -> str | None:
        value = self._row(line).get("unit_cost")
        return None if value is None else str(value)

    def get_cost(self, line) -> str | None:
        value = self._row(line).get("cost")
        return None if value is None else str(value)


class CostingSerializer(serializers.Serializer):
    batch_cost = serializers.DecimalField(max_digits=18, decimal_places=2)
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=4, help_text="Cost of one finished unit")
    sale_price = serializers.DecimalField(max_digits=18, decimal_places=4)
    margin = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    margin_percent = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True)


class BillOfMaterialsSerializer(serializers.ModelSerializer):
    product_id = WorkspaceRelatedField(Product, source="product")
    product_name = serializers.CharField(source="product.name", read_only=True)
    lines = ComponentSerializer(many=True)
    made_to_order = serializers.BooleanField(source="product.made_to_order", read_only=True)
    costing = serializers.SerializerMethodField()

    def _costing(self, bom):
        cache = self.__dict__.setdefault("_costs", {})
        if bom.pk not in cache:
            from .services import costing

            cache[bom.pk] = costing(bom)
        return cache[bom.pk]

    @extend_schema_field(CostingSerializer)
    def get_costing(self, bom):
        return CostingSerializer(self._costing(bom)).data

    class Meta:
        model = BillOfMaterials
        fields = ["id", "product_id", "product_name", "name", "output_quantity", "notes", "is_active", "lines", "made_to_order", "costing", "created_at"]
        read_only_fields = ["id", "product_name", "made_to_order", "costing", "created_at"]

    def validate(self, attrs):
        product = attrs.get("product", getattr(self.instance, "product", None))
        if product is not None and not (product.track_inventory or product.made_to_order):
            raise serializers.ValidationError({"product_id": ["The finished product must track stock, or be made to order."]})
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
