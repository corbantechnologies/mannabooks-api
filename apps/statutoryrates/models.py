from django.db import models

from apps.core.models import WorkspaceModel


class StatutoryRate(WorkspaceModel):
    """
    Kenya's payroll rates from a date: PAYE bands and relief, SHIF, NSSF and the Affordable Housing Levy.
    Payroll uses the set in force on the pay date. Seeded with the rates MannaBooks knows; check them
    against KRA and NSSF notices and add a new set when the law changes.
    """

    effective_from = models.DateField()
    paye_bands = models.JSONField(help_text='[{"upto": 24000, "rate": 10}, ..., {"upto": null, "rate": 35}] monthly, KES')
    personal_relief = models.DecimalField(max_digits=10, decimal_places=2, default=2400)
    shif_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.75)
    shif_minimum = models.DecimalField(max_digits=10, decimal_places=2, default=300)
    nssf_rate = models.DecimalField(max_digits=5, decimal_places=2, default=6, help_text="Each of employee and employer")
    nssf_lower_limit = models.DecimalField(max_digits=12, decimal_places=2, default=8000)
    nssf_upper_limit = models.DecimalField(max_digits=12, decimal_places=2, default=72000)
    housing_levy_rate = models.DecimalField(max_digits=5, decimal_places=2, default=1.5, help_text="Each of employee and employer")
    deductions_before_paye = models.BooleanField(default=True, help_text="SHIF and the Housing Levy reduce taxable pay (since Dec 2024)")
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-effective_from"]
        constraints = [models.UniqueConstraint(fields=["workspace", "effective_from"], name="one_rate_set_per_date")]

    def __str__(self):
        return f"Rates from {self.effective_from}"
