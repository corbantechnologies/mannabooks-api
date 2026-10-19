from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class Project(WorkspaceModel):
    """
    A job or contract whose income and costs are tracked together (job costing). Invoices, bills,
    expenses and journal lines tagged with it make up its profit.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="projects")
    manager = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    contract_value = models.DecimalField(**MONEY_FIELD, default=0, help_text="What the customer pays, before VAT")
    cost_budget = models.DecimalField(**MONEY_FIELD, default=0, help_text="What the job should cost")
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["workspace", "code"], name="unique_project_code")]

    def __str__(self):
        return f"{self.code} {self.name}"
