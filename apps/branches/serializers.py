from rest_framework import serializers

from apps.core.codes import AutoCodeMixin

from .models import Branch


class BranchSerializer(AutoCodeMixin, serializers.ModelSerializer):
    code_key = "branch"

    class Meta:
        model = Branch
        fields = ["id", "name", "code", "address", "phone", "is_default", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"code": {"required": False, "allow_blank": True, "help_text": "Blank: numbered for you (BR-01)"}}

    def validate_code(self, value):
        value = value.strip().upper()
        if not value:
            return value
        clash = Branch.objects.filter(workspace=self.context["workspace"], code=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Another branch already uses this code.")
        return value

    def validate(self, attrs):
        if self.instance and self.instance.is_default and attrs.get("is_active") is False:
            raise serializers.ValidationError({"is_active": ["Make another branch the default before closing this one."]})
        return attrs
