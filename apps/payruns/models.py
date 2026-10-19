from django.conf import settings
from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class PayRun(WorkspaceModel):
    """
    One month's payroll. Draft: payslips can be changed. Approved: posted to the books (salaries, PAYE,
    SHIF, NSSF, Housing Levy). Paid: net pay sent from a bank or M-Pesa account.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"

    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    pay_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    gross_pay = models.DecimalField(**MONEY_FIELD, default=0)
    total_paye = models.DecimalField(**MONEY_FIELD, default=0)
    total_shif = models.DecimalField(**MONEY_FIELD, default=0)
    total_nssf = models.DecimalField(**MONEY_FIELD, default=0, help_text="Employee and employer")
    total_housing_levy = models.DecimalField(**MONEY_FIELD, default=0, help_text="Employee and employer")
    total_other_deductions = models.DecimalField(**MONEY_FIELD, default=0)
    net_pay = models.DecimalField(**MONEY_FIELD, default=0)
    employer_cost = models.DecimalField(**MONEY_FIELD, default=0, help_text="Gross plus employer NSSF and Housing Levy")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_from = models.ForeignKey("bankaccounts.BankAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    paid_at = models.DateField(null=True, blank=True)
    remittances = models.JSONField(default=dict, blank=True, help_text="Statutory amounts paid: {kind: {amount, date, reference}}")

    class Meta:
        ordering = ["-year", "-month"]
        constraints = [models.UniqueConstraint(fields=["workspace", "year", "month"], name="one_pay_run_per_month")]

    def __str__(self):
        return f"Payroll {self.year}-{self.month:02d}"
