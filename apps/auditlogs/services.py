"""Recording changes. Views call `record`; `snapshot` and `diff` describe what changed."""
from decimal import Decimal

from .models import AuditLog

SKIP_FIELDS = {"password", "updated_at", "created_at"}


def snapshot(instance) -> dict:
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in SKIP_FIELDS:
            continue
        value = getattr(instance, field.attname)
        if isinstance(value, Decimal):
            value = str(value)
        elif value is not None and not isinstance(value, (str, int, float, bool, list, dict)):
            value = str(value)
        data[field.name] = value
    return data


def diff(before: dict, after: dict) -> dict:
    return {key: {"from": before.get(key), "to": value} for key, value in after.items() if before.get(key) != value}


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR") or None


def record(request, action: str, instance, changes: dict | None = None) -> AuditLog:
    workspace = getattr(request, "workspace", None) or getattr(instance, "workspace", None)
    user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    if changes is None:
        changes = {} if action == "delete" else snapshot(instance)
    return AuditLog.objects.create(
        workspace=workspace,
        actor=user,
        action=action,
        model=instance._meta.label,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        changes=changes,
        ip_address=_client_ip(request),
    )
