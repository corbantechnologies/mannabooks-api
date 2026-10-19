from apps.core.exceptions import BusinessRuleError

from .models import Warehouse


def default_warehouse(workspace, branch=None) -> Warehouse:
    """Where a sale takes stock from: the branch's warehouse, else the default one (created if there is none)."""
    if branch is not None:
        found = Warehouse.objects.filter(workspace=workspace, branch=branch, is_active=True).order_by("-is_default").first()
        if found:
            return found
    found = Warehouse.objects.filter(workspace=workspace, is_default=True).first()
    if found is None:
        if Warehouse.objects.filter(workspace=workspace).exists():
            raise BusinessRuleError("Choose a default warehouse in Inventory > Warehouses.")
        found = Warehouse.objects.create(workspace=workspace, name="Main store", code="MAIN", is_default=True)
    if not found.is_active:
        raise BusinessRuleError(f"The default warehouse {found} is inactive.")
    return found
