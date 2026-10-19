from django.db import models

from apps.core.models import WorkspaceModel


class LedgerAccount(WorkspaceModel):
    """An account in the chart of accounts. Its balance is the sum of its posted journal lines."""

    class Type(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    class Subtype(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank and mobile money"
        RECEIVABLE = "receivable", "Accounts receivable"
        INVENTORY = "inventory", "Inventory"
        CURRENT_ASSET = "current_asset", "Other current asset"
        FIXED_ASSET = "fixed_asset", "Fixed asset"
        TAX_ASSET = "tax_asset", "Tax recoverable"
        PAYABLE = "payable", "Accounts payable"
        TAX_LIABILITY = "tax_liability", "Tax payable"
        CURRENT_LIABILITY = "current_liability", "Other current liability"
        LONG_TERM_LIABILITY = "long_term_liability", "Long-term liability"
        EQUITY = "equity", "Equity"
        INCOME = "income", "Operating income"
        OTHER_INCOME = "other_income", "Other income"
        COST_OF_SALES = "cost_of_sales", "Cost of sales"
        EXPENSE = "expense", "Operating expense"
        OTHER_EXPENSE = "other_expense", "Other expense"

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=20, choices=Type.choices)
    subtype = models.CharField(max_length=30, choices=Subtype.choices)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    description = models.CharField(max_length=255, blank=True)
    system_key = models.CharField(
        max_length=40, blank=True, help_text="Set on accounts the system posts to (sales, receivable, VAT, ...)."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "code"], name="unique_account_code_per_workspace"),
            models.UniqueConstraint(
                fields=["workspace", "system_key"], condition=~models.Q(system_key=""), name="unique_system_key_per_workspace"
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.name}"

    @property
    def is_debit_normal(self) -> bool:
        return self.account_type in (self.Type.ASSET, self.Type.EXPENSE)

    @property
    def is_system(self) -> bool:
        return bool(self.system_key)
