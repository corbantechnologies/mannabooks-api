from django.db import models

from apps.core.models import WorkspaceModel


class Employee(WorkspaceModel):
    """
    The HR record for a member of staff. It may be linked to a membership (the person can sign in),
    or not (staff without a login). The pay fields feed payroll.
    """

    class PayMethod(models.TextChoices):
        BANK = "bank", "Bank transfer"
        MPESA = "mpesa", "M-Pesa"
        CASH = "cash", "Cash"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        EXITED = "exited", "Exited"

    staff_number = models.CharField(max_length=30)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    other_names = models.CharField(max_length=80, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    national_id = models.CharField(max_length=20, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    department = models.ForeignKey(
        "departments.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="employees"
    )
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="employees")
    reports_to = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="direct_reports",
        help_text="Their supervisor. Approvals and work reports follow this line.",
    )
    membership = models.OneToOneField(
        "memberships.Membership", null=True, blank=True, on_delete=models.SET_NULL, related_name="employee"
    )
    hire_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    # pay
    on_payroll = models.BooleanField(default=False, help_text="Paid through MannaBooks payroll")
    basic_salary = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="Monthly")
    recurring_items = models.JSONField(default=list, blank=True,
                                       help_text='Allowances and deductions every month: [{"name", "kind": "earning"|"deduction", "amount", "taxable"}]')
    pay_method = models.CharField(max_length=10, choices=PayMethod.choices, default=PayMethod.BANK)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=40, blank=True)
    mpesa_phone = models.CharField(max_length=20, blank=True)
    nssf_number = models.CharField("NSSF number", max_length=30, blank=True)
    shif_number = models.CharField("SHIF number", max_length=30, blank=True)
    annual_leave_days = models.DecimalField(max_digits=5, decimal_places=1, default=21, help_text="A year (the law's minimum is 21 working days)")
    exit_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["first_name", "last_name"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "staff_number"], name="unique_staff_number_per_workspace")
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self) -> str:
        return " ".join(part for part in [self.first_name, self.other_names, self.last_name] if part)
