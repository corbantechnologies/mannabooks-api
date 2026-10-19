from django.db import models

from apps.core.models import WorkspaceModel

# (name, abbreviation, KRA eTIMS quantity unit code). Codes can be edited; check them against KRA's code list.
DEFAULT_UNITS = [
    ("Piece", "pcs", "U"), ("Kilogram", "kg", "KG"), ("Gram", "g", ""), ("Litre", "l", ""), ("Millilitre", "ml", ""),
    ("Metre", "m", ""), ("Box", "box", ""), ("Pack", "pack", ""), ("Bag", "bag", ""), ("Dozen", "doz", ""),
    ("Hour", "hr", ""), ("Day", "day", ""), ("Service", "svc", ""),
]


class Unit(WorkspaceModel):
    """A unit products are sold in. Products keep the abbreviation, so renaming a unit never breaks them."""

    name = models.CharField(max_length=60)
    abbreviation = models.CharField(max_length=20)
    etims_code = models.CharField("KRA eTIMS unit code", max_length=10, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "abbreviation"], name="unique_unit_abbreviation")]

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"
