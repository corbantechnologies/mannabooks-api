from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class Payslip(WorkspaceModel):
    """One employee's pay for a month. `items` holds allowances and deductions; statutory amounts are worked out."""

    pay_run = models.ForeignKey("payruns.PayRun", on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="payslips")
    basic_salary = models.DecimalField(**MONEY_FIELD, default=0)
    unpaid_leave_days = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    unpaid_leave_deduction = models.DecimalField(**MONEY_FIELD, default=0)
    items = models.JSONField(default=list, blank=True, help_text='[{"name", "kind": "earning"|"deduction", "amount", "taxable"}]')
    gross_pay = models.DecimalField(**MONEY_FIELD, default=0)
    taxable_pay = models.DecimalField(**MONEY_FIELD, default=0)
    nssf_employee = models.DecimalField(**MONEY_FIELD, default=0)
    nssf_employer = models.DecimalField(**MONEY_FIELD, default=0)
    shif = models.DecimalField(**MONEY_FIELD, default=0)
    housing_levy_employee = models.DecimalField(**MONEY_FIELD, default=0)
    housing_levy_employer = models.DecimalField(**MONEY_FIELD, default=0)
    paye_before_relief = models.DecimalField(**MONEY_FIELD, default=0)
    personal_relief = models.DecimalField(**MONEY_FIELD, default=0)
    paye = models.DecimalField(**MONEY_FIELD, default=0)
    other_deductions = models.DecimalField(**MONEY_FIELD, default=0)
    net_pay = models.DecimalField(**MONEY_FIELD, default=0)
    # what the employee was, at the time
    employee_name = models.CharField(max_length=200)
    staff_number = models.CharField(max_length=30)
    kra_pin = models.CharField(max_length=20, blank=True)
    pay_method = models.CharField(max_length=10, blank=True)
    pay_to = models.CharField(max_length=120, blank=True, help_text="Bank account or M-Pesa number")

    class Meta:
        ordering = ["employee_name"]
        constraints = [models.UniqueConstraint(fields=["pay_run", "employee"], name="one_payslip_per_employee_per_run")]

    def __str__(self):
        return f"{self.employee_name} {self.pay_run}"
