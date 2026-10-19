from django.db import models

from apps.core.models import WorkspaceModel
from apps.core.money import MONEY_FIELD


class FixedAsset(WorkspaceModel):
    """
    Something the business owns and uses for more than a year: vehicles, computers, furniture, machinery,
    buildings. Its cost is spread over its useful life by monthly depreciation.
    """

    class Category(models.TextChoices):
        LAND = "land", "Land"
        BUILDINGS = "buildings", "Buildings"
        MOTOR_VEHICLES = "motor_vehicles", "Motor vehicles"
        FURNITURE = "furniture", "Furniture and fittings"
        COMPUTERS = "computers", "Computers and IT equipment"
        PLANT = "plant", "Plant and machinery"
        OFFICE_EQUIPMENT = "office_equipment", "Office equipment"
        OTHER = "other", "Other"

    class Method(models.TextChoices):
        STRAIGHT_LINE = "straight_line", "Straight line (same amount each month)"
        REDUCING_BALANCE = "reducing_balance", "Reducing balance (a percentage of what is left)"
        NONE = "none", "Not depreciated (e.g. land)"

    class Acquisition(models.TextChoices):
        RECORDED = "recorded", "The purchase is already in the books (bill or expense)"
        EXISTING = "existing", "Owned before we started using MannaBooks"

    class Status(models.TextChoices):
        ACTIVE = "active", "In use"
        FULLY_DEPRECIATED = "fully_depreciated", "Fully depreciated"
        DISPOSED = "disposed", "Sold or scrapped"

    number = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    serial_number = models.CharField(max_length=80, blank=True, help_text="Serial, chassis or registration number")
    location = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    custodian = models.ForeignKey("employees.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                  help_text="Who looks after it")
    cost_center = models.ForeignKey("costcenters.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    supplier = models.ForeignKey("suppliers.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    bill = models.ForeignKey("bills.Bill", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    asset_account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    accumulated_account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    expense_account = models.ForeignKey("ledgeraccounts.LedgerAccount", on_delete=models.PROTECT, related_name="+")
    acquisition = models.CharField(max_length=10, choices=Acquisition.choices, default=Acquisition.RECORDED)
    purchase_date = models.DateField()
    in_service_date = models.DateField(help_text="Depreciation starts in this month")
    cost = models.DecimalField(**MONEY_FIELD)
    residual_value = models.DecimalField(**MONEY_FIELD, default=0, help_text="What it should be worth at the end of its life")
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.STRAIGHT_LINE)
    useful_life_months = models.PositiveIntegerField(default=60)
    rate_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text="Yearly rate, for reducing balance")
    opening_accumulated = models.DecimalField(**MONEY_FIELD, default=0, help_text="Depreciation charged before MannaBooks (existing assets)")
    accumulated_depreciation = models.DecimalField(**MONEY_FIELD, default=0)
    depreciated_to = models.DateField(null=True, blank=True, help_text="Last month end depreciated")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    disposal_date = models.DateField(null=True, blank=True)
    disposal_proceeds = models.DecimalField(**MONEY_FIELD, default=0)
    disposal_account = models.ForeignKey("bankaccounts.BankAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    disposal_gain = models.DecimalField(**MONEY_FIELD, default=0, help_text="Proceeds less book value (negative: a loss)")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["workspace", "number"], name="unique_fixed_asset_number")]

    def __str__(self):
        return f"{self.number} {self.name}"

    @property
    def book_value(self):
        return self.cost - self.accumulated_depreciation
