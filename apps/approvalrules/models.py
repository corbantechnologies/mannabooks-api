from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD

DOCUMENT_TYPES = [
    ("purchase_order", "Purchase orders"),
    ("service_order", "Service orders"),
    ("payment_voucher", "Payment vouchers"),
    ("pay_run", "Payroll"),
    ("budget", "Budgets"),
]
LEVEL_KINDS = {
    "supervisor": "Their supervisor",
    "department_head": "Their department head",
    "module_in_charge": "The module in-charge",
    "role": "Anyone with a role",
    "member": "A named person",
    "owner": "The owner",
}


class ApprovalRule(WorkspaceModel):
    """
    Who must approve a kind of document, level by level, when its amount falls in a band. A document
    that matches no rule is approved directly by anyone with the approve permission.
    """

    name = models.CharField(max_length=120)
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPES)
    min_amount = models.DecimalField(**MONEY_FIELD, default=0, help_text="Applies from this amount")
    max_amount = models.DecimalField(**MONEY_FIELD, null=True, blank=True, help_text="Up to this amount. Blank: no upper limit")
    levels = models.JSONField(default=list, help_text='In order: [{"kind": "supervisor"|"department_head"|"module_in_charge"|"role"|"member"|"owner", '
                                                      '"role_id"?, "membership_id"?}]')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["document_type", "min_amount"]

    def __str__(self):
        return self.name
