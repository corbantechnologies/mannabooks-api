"""Codes people may leave blank (SKUs, department and branch codes...): the next free number from the sequence."""
from apps.core.exceptions import BusinessRuleError


def next_code(model, workspace, key: str, field: str = "code") -> str:
    from apps.sequences.services import next_value

    for _ in range(100):  # skip numbers someone already typed by hand
        code = next_value(workspace, key)
        if not model.objects.filter(workspace=workspace, **{f"{field}__iexact": code}).exists():
            return code
    raise BusinessRuleError("Couldn't find a free code. Type one in.")


class AutoCodeMixin:
    """For a ModelSerializer with a `code` field: a blank code gets the next one from the `code_key` sequence."""

    code_key = ""

    def _fill_code(self, validated, workspace):
        if self.instance is None or "code" in validated:
            if not (validated.get("code") or "").strip():
                validated["code"] = next_code(self.Meta.model, workspace, self.code_key)

    def create(self, validated_data):
        self._fill_code(validated_data, validated_data["workspace"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._fill_code(validated_data, instance.workspace)
        return super().update(instance, validated_data)
