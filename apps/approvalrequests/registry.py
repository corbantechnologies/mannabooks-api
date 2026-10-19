"""The documents that can go through an approval chain, and how to read and approve each one."""
import calendar
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module

from django.apps import apps

from apps.core.catalog import DEPARTMENT_MODULES


def _call(path: str):
    module, _, name = path.partition(":")
    return getattr(import_module(module), name)


@dataclass(frozen=True)
class DocType:
    label: str
    model: str
    module: str  # department module whose head is the in-charge
    submit_perm: str
    path: str  # web page, with {id}
    amount: Callable
    number: Callable
    summary: Callable
    approve: Callable  # (document, user) -> document
    waiting: Callable  # document is in the state that needs approval

    def get(self, workspace, pk):
        return apps.get_model(self.model).objects.filter(workspace=workspace, pk=pk).first()


def _budget_total(b):
    return sum((line.total for line in b.lines.select_related("account") if line.account.account_type == "expense"), 0)


DOCS: dict[str, DocType] = {
    "purchase_order": DocType(
        "Purchase order", "purchaseorders.PurchaseOrder", "purchasing", "purchaseorders.create", "/purchasing/orders/{id}",
        lambda o: o.total, lambda o: o.number, lambda o: str(o.supplier), lambda o, u: _call("apps.purchaseorders.services:approve")(o, u),
        lambda o: o.status == "draft"),
    "service_order": DocType(
        "Service order", "serviceorders.ServiceOrder", "purchasing", "purchaseorders.create", "/purchasing/service-orders/{id}",
        lambda o: o.total, lambda o: o.number, lambda o: str(o.supplier), lambda o, u: _call("apps.serviceorders.services:act")(o, "approve", u),
        lambda o: o.status == "draft"),
    "payment_voucher": DocType(
        "Payment voucher", "paymentvouchers.PaymentVoucher", "finance", "paymentvouchers.create", "/purchasing/vouchers/{id}",
        lambda o: o.total, lambda o: o.number, lambda o: f"Pay {o.supplier}", lambda o, u: _call("apps.paymentvouchers.services:approve")(o, u),
        lambda o: o.status == "draft"),
    "pay_run": DocType(
        "Payroll", "payruns.PayRun", "hr", "payroll.manage", "/payroll/{id}",
        lambda o: o.employer_cost, lambda o: f"Payroll {calendar.month_name[o.month]} {o.year}", lambda o: f"Net pay {o.net_pay:,.2f}",
        lambda o, u: _call("apps.payruns.services:approve")(o, u), lambda o: o.status == "draft"),
    "budget": DocType(
        "Budget", "budgets.Budget", "finance", "budgets.manage", "/accounting/budgets/{id}",
        _budget_total, lambda o: o.name, lambda o: f"{o.fiscal_year} spending", lambda o, u: _call("apps.budgets.services:approve")(o, u),
        lambda o: o.status == "draft"),
}


def module_label(module: str) -> str:
    return f"The {DEPARTMENT_MODULES.get(module, module).lower()} in-charge" if module else "The module in-charge"
