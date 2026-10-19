from django.utils.text import slugify
from rest_framework import serializers

from apps.core.catalog import is_valid_code

from .models import Role


class RoleSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Role
        fields = ["id", "name", "slug", "description", "permissions", "is_preset", "member_count", "created_at"]
        read_only_fields = ["id", "slug", "is_preset", "member_count", "created_at"]

    def validate_permissions(self, value):
        if not isinstance(value, list) or not all(isinstance(code, str) for code in value):
            raise serializers.ValidationError("Send a list of permission codes such as \"employees.view\".")
        unknown = [code for code in value if not is_valid_code(code)]
        if unknown:
            raise serializers.ValidationError(f"Unknown permissions: {', '.join(unknown)}.")
        return sorted(set(value))

    def validate_name(self, value):
        value = value.strip()
        workspace = self.context["workspace"]
        clash = Role.objects.filter(workspace=workspace, slug=slugify(value))
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A role with this name already exists.")
        return value

    def create(self, validated_data):
        validated_data["slug"] = slugify(validated_data["name"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if instance.slug == "owner" and "permissions" in validated_data:
            raise serializers.ValidationError({"permissions": ["The Owner role always has full access."]})
        if "name" in validated_data and not instance.is_preset:
            validated_data["slug"] = slugify(validated_data["name"])
        elif instance.is_preset:
            validated_data.pop("name", None)  # preset names stay so the app can rely on them
        return super().update(instance, validated_data)


class PermissionModuleSerializer(serializers.Serializer):
    module = serializers.CharField()
    label = serializers.CharField()
    actions = serializers.ListField(child=serializers.CharField())


class PermissionCatalogSerializer(serializers.Serializer):
    modules = PermissionModuleSerializer(many=True)
    department_modules = serializers.DictField(child=serializers.CharField())
